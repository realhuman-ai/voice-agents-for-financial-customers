-- ============================================
-- Voice Scheduling Platform - Supabase Schema
-- Run this in Supabase SQL Editor
-- ============================================

-- Businesses (restaurant, oil change, clinic, etc.)
CREATE TABLE IF NOT EXISTS businesses (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('restaurant', 'oil_change', 'clinic', 'salon', 'other')),
    phone TEXT,
    settings JSONB DEFAULT '{"slot_capacity": 1, "slot_duration_minutes": 60}',
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Appointments / Reservations (all business types share this table)
CREATE TABLE IF NOT EXISTS appointments (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    business_id UUID REFERENCES businesses(id) ON DELETE CASCADE,
    customer_name TEXT NOT NULL,
    customer_phone TEXT,
    appointment_date DATE NOT NULL,
    appointment_time TIME NOT NULL,
    party_size INT DEFAULT 1,
    status TEXT DEFAULT 'confirmed' CHECK (status IN ('confirmed', 'cancelled', 'completed', 'no_show')),
    notes TEXT,
    metadata JSONB DEFAULT '{}',  -- car info, medical reason, etc.
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Waitlist (up to 5 per slot per business)
CREATE TABLE IF NOT EXISTS waitlist (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    business_id UUID REFERENCES businesses(id) ON DELETE CASCADE,
    customer_name TEXT NOT NULL,
    customer_phone TEXT,
    requested_date DATE NOT NULL,
    requested_time TIME,
    party_size INT DEFAULT 1,
    position INT NOT NULL,
    status TEXT DEFAULT 'waiting' CHECK (status IN ('waiting', 'notified', 'booked', 'cancelled')),
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for fast lookups
CREATE INDEX IF NOT EXISTS idx_appointments_business_date
    ON appointments(business_id, appointment_date, appointment_time);

CREATE INDEX IF NOT EXISTS idx_waitlist_business_date
    ON waitlist(business_id, requested_date, status);

-- ============================================
-- Seed data - Insert your businesses
-- ============================================

INSERT INTO businesses (name, type, phone, settings) VALUES
(
    'Biryani Paradise',
    'restaurant',
    '+15822599600',
    '{"slot_capacity": 4, "slot_duration_minutes": 90, "max_party_size": 10}'
),
(
    'Quick Lube',
    'oil_change',
    '',
    '{"slot_capacity": 3, "slot_duration_minutes": 45}'
),
(
    'City Clinic',
    'clinic',
    '',
    '{"slot_capacity": 1, "slot_duration_minutes": 30}'
);

-- View business IDs after insert (copy these to your config files)
SELECT id, name, type FROM businesses;
