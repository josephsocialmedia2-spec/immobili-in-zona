-- ACQUISIZIONE SUSA CRM — schema online
-- Eseguire nel SQL Editor di un progetto Supabase dedicato.

create extension if not exists pgcrypto;

create table if not exists public.leads (
  id text primary key,
  owner_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
  first_name text default '', last_name text default '', company text default '', phone text default '', email text default '',
  comune text default 'Susa', cap text default '', street text default '', civic text default '', full_address text default '',
  property_type text default '', sqm numeric, rooms text default '', features text default '', current_price numeric, previous_price numeric,
  source text default '', source_url text default '', seller_signal text default '', seller_type text default '', priority text default 'Media',
  confidence numeric, contact_status text default 'Da contattare', next_action text default '', callback_at timestamptz,
  original_note text default '', privacy_rule text default '', qualification_class text default '',
  created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);

create table if not exists public.notes (
  id text primary key,
  owner_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
  lead_id text not null references public.leads(id) on delete cascade,
  body text not null, contact_type text default '', outcome text default '', next_action text default '', callback_at timestamptz,
  missing_note_reason text default '', created_at timestamptz not null default now()
);

create table if not exists public.reminders (
  id text primary key,
  owner_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
  lead_id text references public.leads(id) on delete cascade,
  title text not null, due_at timestamptz not null, status text default 'Aperto', priority text default 'Media',
  created_at timestamptz not null default now(), completed_at timestamptz
);

create table if not exists public.prequalifications (
  id text primary key,
  owner_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
  lead_id text not null references public.leads(id) on delete cascade,
  answers_json jsonb not null default '{}'::jsonb, class text not null check (class in ('A','B','C')),
  action text not null, created_at timestamptz not null default now()
);

create table if not exists public.audit_log (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
  entity_type text not null, entity_id text not null, action text not null, snapshot_json jsonb not null,
  created_at timestamptz not null default now()
);

create index if not exists leads_owner_callback_idx on public.leads(owner_id, callback_at);
create index if not exists leads_owner_phone_idx on public.leads(owner_id, phone);
create index if not exists reminders_owner_due_idx on public.reminders(owner_id, status, due_at);
create index if not exists notes_owner_lead_idx on public.notes(owner_id, lead_id, created_at desc);

alter table public.leads enable row level security;
alter table public.notes enable row level security;
alter table public.reminders enable row level security;
alter table public.prequalifications enable row level security;
alter table public.audit_log enable row level security;

create policy "owner manages leads" on public.leads for all using (owner_id = auth.uid()) with check (owner_id = auth.uid());
create policy "owner reads notes" on public.notes for select using (owner_id = auth.uid());
create policy "owner appends notes" on public.notes for insert with check (owner_id = auth.uid());
create policy "owner manages reminders" on public.reminders for all using (owner_id = auth.uid()) with check (owner_id = auth.uid());
create policy "owner reads prequalifications" on public.prequalifications for select using (owner_id = auth.uid());
create policy "owner appends prequalifications" on public.prequalifications for insert with check (owner_id = auth.uid());
create policy "owner reads audit" on public.audit_log for select using (owner_id = auth.uid());
create policy "owner appends audit" on public.audit_log for insert with check (owner_id = auth.uid());

-- Lo storico non va riscritto: note, prequalifiche e audit sono append-only.
revoke update, delete on public.notes from authenticated;
revoke update, delete on public.prequalifications from authenticated;
revoke update, delete on public.audit_log from authenticated;

create or replace function public.write_lead_audit() returns trigger language plpgsql security invoker as $$
begin
  insert into public.audit_log(owner_id, entity_type, entity_id, action, snapshot_json)
  values (new.owner_id, 'lead', new.id, lower(tg_op), to_jsonb(new));
  return new;
end;
$$;

drop trigger if exists lead_audit on public.leads;
create trigger lead_audit after insert or update on public.leads for each row execute function public.write_lead_audit();
