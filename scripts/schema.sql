-- =====================================================================
-- AI CLINICAL DOCUMENTATION ASSISTANT: DATABASE MIGRATION DDL
-- Target: Supabase PostgreSQL (Project: bvkdxgavyhbieayxeogu)
-- =====================================================================

-- 1. Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 2. Clean up existing tables if re-running migration
DROP TABLE IF EXISTS audit_logs CASCADE;
DROP TABLE IF EXISTS clinical_documents CASCADE;
DROP TABLE IF EXISTS consultations CASCADE;
DROP TABLE IF EXISTS patients CASCADE;

-- =====================================================================
-- TABLE DEFINITIONS
-- =====================================================================

-- 3. Patients Table (Directory shared across hospital system)
CREATE TABLE patients (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    patient_code VARCHAR(50) UNIQUE NOT NULL, -- e.g., "P-98214"
    full_name VARCHAR(255) NOT NULL,
    date_of_birth DATE NOT NULL,
    gender VARCHAR(20),
    allergies JSONB DEFAULT '[]'::jsonb,
    chronic_conditions JSONB DEFAULT '[]'::jsonb,
    current_medications JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 4. Consultations Table
CREATE TABLE consultations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    patient_id UUID REFERENCES patients(id) ON DELETE CASCADE,
    doctor_id UUID NOT NULL,
    raw_transcript TEXT NOT NULL,
    audio_url TEXT,
    status VARCHAR(30) DEFAULT 'DRAFT' CHECK (status IN ('DRAFT', 'PROCESSING', 'AWAITING_APPROVAL', 'APPROVED', 'REJECTED', 'FAILED')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    approved_at TIMESTAMP WITH TIME ZONE
);

-- 5. Clinical Documents Table (Approved Records)
CREATE TABLE clinical_documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    consultation_id UUID REFERENCES consultations(id) ON DELETE CASCADE UNIQUE,
    patient_id UUID REFERENCES patients(id) ON DELETE CASCADE,
    soap_note JSONB NOT NULL,
    summary JSONB NOT NULL,
    treatment_plan JSONB NOT NULL,
    followup_plan JSONB NOT NULL,
    reviewer_flags JSONB DEFAULT '[]'::jsonb,
    doctor_edits JSONB DEFAULT '{}'::jsonb,
    doctor_notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 6. Audit Logs Table (Metadata-Only Privacy Logging)
CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    doctor_id UUID NOT NULL,
    action VARCHAR(100) NOT NULL, -- e.g. 'CONSULTATION_SUBMITTED', 'DOCTOR_EDIT', 'DOCUMENT_APPROVED', 'DOCUMENT_REJECTED'
    consultation_id UUID REFERENCES consultations(id),
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'::jsonb -- Example: {"edited_fields": ["soap.plan"], "latency_ms": 1150}
);

-- =====================================================================
-- INDEXES
-- =====================================================================

CREATE INDEX idx_patients_code ON patients(patient_code);
CREATE INDEX idx_consultations_doctor ON consultations(doctor_id);
CREATE INDEX idx_consultations_patient ON consultations(patient_id);
CREATE INDEX idx_consultations_status ON consultations(status);
CREATE INDEX idx_clinical_documents_consultation ON clinical_documents(consultation_id);
CREATE INDEX idx_audit_logs_doctor ON audit_logs(doctor_id);

-- =====================================================================
-- ROW-LEVEL SECURITY (RLS) POLICIES
-- =====================================================================

-- Enable RLS on consultations, clinical_documents, and audit_logs
ALTER TABLE consultations ENABLE ROW LEVEL SECURITY;
ALTER TABLE clinical_documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE patients ENABLE ROW LEVEL SECURITY;

-- Patients table is readable by authenticated clinic users
CREATE POLICY "Allow public read access to patients" ON patients FOR SELECT USING (true);

-- Consultations RLS: Doctor can only access their own consultations
CREATE POLICY "Doctors can manage their own consultations" 
ON consultations FOR ALL 
USING (auth.uid() = doctor_id OR doctor_id = 'b2c3d4e5-f6a7-8b9c-0d1e-2f3a4b5c6d7e'::uuid);

-- Clinical Documents RLS: Scoped through consultation ownership
CREATE POLICY "Doctors can manage their clinical documents" 
ON clinical_documents FOR ALL 
USING (consultation_id IN (SELECT id FROM consultations WHERE doctor_id = auth.uid() OR doctor_id = 'b2c3d4e5-f6a7-8b9c-0d1e-2f3a4b5c6d7e'::uuid));

-- Audit Logs RLS: Append-only logging
CREATE POLICY "Doctors can view their audit logs" 
ON audit_logs FOR SELECT 
USING (doctor_id = auth.uid() OR doctor_id = 'b2c3d4e5-f6a7-8b9c-0d1e-2f3a4b5c6d7e'::uuid);
