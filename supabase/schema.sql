-- TransitHear Supabase Schema
-- Idempotent: safe to run multiple times
-- Enable required extensions
create extension if not exists "pgcrypto";

-- ============================================================
-- stations
-- ============================================================
create table if not exists stations (
    code        text primary key,
    name        text not null,
    aliases     text[],
    city        text,
    lat         float8,
    lng         float8,
    platform_count int default 4
);
alter table stations enable row level security;

-- ============================================================
-- trains
-- ============================================================
create table if not exists trains (
    number      text primary key,
    name        text not null,
    aliases     text[],
    origin_code text references stations(code),
    dest_code   text references stations(code)
);
alter table trains enable row level security;

-- ============================================================
-- train_stops
-- ============================================================
create table if not exists train_stops (
    train_number    text references trains(number),
    seq             int not null,
    station_code    text references stations(code),
    arr             time,
    dep             time,
    platform        int,
    primary key (train_number, seq)
);
alter table train_stops enable row level security;

-- ============================================================
-- journeys
-- ============================================================
create table if not exists journeys (
    id              uuid primary key default gen_random_uuid(),
    device_id       text not null,
    mode            text check (mode in ('booking','route')) not null,
    train_number    text,
    origin_code     text,
    dest_code       text,
    boarding_date   date,
    status          text default 'active',
    created_at      timestamptz default now()
);
alter table journeys enable row level security;

-- ============================================================
-- official_updates
-- ============================================================
create table if not exists official_updates (
    id              uuid primary key default gen_random_uuid(),
    train_number    text,
    station_code    text,
    kind            text check (kind in ('platform_change','delay','early_arrival','cancellation')),
    new_platform    int,
    delay_minutes   int,
    source          text default 'simulated',
    effective_at    timestamptz default now()
);
alter table official_updates enable row level security;

-- ============================================================
-- announcements
-- ============================================================
create table if not exists announcements (
    id                      uuid primary key default gen_random_uuid(),
    journey_id              uuid references journeys(id),
    device_id               text not null,
    raw_transcript          text,   -- always null (R7: never store audio)
    normalized_transcript   text,
    stt_source              text,
    stt_confidence          float8,
    language                text,
    extracted               jsonb,
    resolved_train          text,
    resolution              jsonb,
    verification            jsonb,
    confidence_final        float8,
    decision                text check (decision in ('alert_critical','alert_info','verify_with_staff','ignore')),
    reason                  text,
    simulated               bool default false,
    acknowledged_at         timestamptz,
    created_at              timestamptz default now()
);
alter table announcements enable row level security;

-- ============================================================
-- audit_log
-- ============================================================
create table if not exists audit_log (
    id              uuid primary key default gen_random_uuid(),
    announcement_id uuid references announcements(id),
    stage_scores    jsonb,
    model_versions  jsonb,
    rules_fired     text[],
    decision        text,
    created_at      timestamptz default now()
);
alter table audit_log enable row level security;

-- ============================================================
-- facilities
-- ============================================================
create table if not exists facilities (
    id                  text primary key,
    station_code        text references stations(code),
    name                text not null,
    type                text,
    status              text check (status in ('present','verified_operational','unverified','outdated','conflicting')),
    last_verified_at    timestamptz,
    source              text
);
alter table facilities enable row level security;

-- ============================================================
-- facility_reports
-- ============================================================
create table if not exists facility_reports (
    id              uuid primary key default gen_random_uuid(),
    facility_id     text references facilities(id),
    device_id       text not null,
    reported_status text,
    note            text,
    created_at      timestamptz default now()
);
alter table facility_reports enable row level security;

-- ============================================================
-- alternatives
-- ============================================================
create table if not exists alternatives (
    id          text primary key,
    from_code   text references stations(code),
    to_code     text references stations(code),
    mode        text,
    description text,
    depart      text,
    arrive      text,
    step_free   bool default false
);
alter table alternatives enable row level security;

-- ============================================================
-- user_preferences
-- ============================================================
create table if not exists user_preferences (
    device_id           text primary key,
    pa_monitoring       bool default true,
    haptic              bool default true,
    sleep_sentinel      bool default false,
    language            text default 'en-IN',
    vibration_patterns  jsonb
);
alter table user_preferences enable row level security;

-- ============================================================
-- emergency_events
-- ============================================================
create table if not exists emergency_events (
    id          uuid primary key default gen_random_uuid(),
    device_id   text,
    kind        text,
    message     text,
    created_at  timestamptz default now()
);
alter table emergency_events enable row level security;

-- No public policies — service role key only, never exposed to browser.
