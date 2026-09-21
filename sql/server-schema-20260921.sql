-- Server schema snapshot for value-investment-agent.
-- Generated from pg_dump --schema-only; contains no table data, secrets, or backups.
-- Generated at UTC: 2026-09-21T00:58:57.9456690Z
--
-- PostgreSQL database dump
--

-- Dumped from database version 16.15
-- Dumped by pg_dump version 16.15

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: backup_audits; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.backup_audits (
    backup_id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    backup_path text NOT NULL,
    sha256 text NOT NULL,
    manifest jsonb NOT NULL,
    restore_status text NOT NULL,
    rto_seconds numeric,
    rpo_seconds numeric,
    verified_at timestamp with time zone,
    CONSTRAINT backup_audits_restore_status_check CHECK ((restore_status = ANY (ARRAY['created'::text, 'passed'::text, 'failed'::text])))
);


--
-- Name: candidate_tracking_observations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.candidate_tracking_observations (
    run_id uuid NOT NULL,
    symbol text NOT NULL,
    source_id uuid NOT NULL,
    quote_as_of timestamp with time zone NOT NULL,
    quote_status text NOT NULL,
    signal_blocked boolean NOT NULL,
    observation jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT candidate_tracking_observations_quote_status_check CHECK ((quote_status = ANY (ARRAY['matched'::text, 'missing_quote'::text, 'invalid_price'::text, 'price_conflict'::text, 'cross_check_missing'::text, 'stale_quote'::text])))
);


--
-- Name: data_points; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.data_points (
    data_point_id uuid NOT NULL,
    symbol text NOT NULL,
    field_name text NOT NULL,
    period_label text NOT NULL,
    value numeric NOT NULL,
    unit text NOT NULL,
    source_id uuid NOT NULL,
    validation_status text NOT NULL,
    human_reviewed boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    CONSTRAINT data_points_validation_status_check CHECK ((validation_status = ANY (ARRAY['pending'::text, 'verified'::text, 'conflict'::text, 'failed'::text])))
);


--
-- Name: filing_candidates; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.filing_candidates (
    candidate_id uuid NOT NULL,
    disclosure_id uuid NOT NULL,
    field_name text NOT NULL,
    value numeric NOT NULL,
    unit text NOT NULL,
    page_number integer NOT NULL,
    source_label text NOT NULL,
    excerpt text NOT NULL,
    parser_version text NOT NULL,
    status text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT filing_candidates_status_check CHECK ((status = ANY (ARRAY['candidate_pending_automated_verification'::text, 'automatically_verified'::text, 'superseded_by_parser'::text])))
);


--
-- Name: financial_enrichment_queue; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.financial_enrichment_queue (
    symbol text NOT NULL,
    screen_date date NOT NULL,
    priority_score numeric NOT NULL,
    status text NOT NULL,
    attempts integer DEFAULT 0 NOT NULL,
    last_error text,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT financial_enrichment_queue_status_check CHECK ((status = ANY (ARRAY['pending_official_filings'::text, 'processing'::text, 'official_filings_archived'::text, 'retry'::text, 'manual_review_required'::text])))
);


--
-- Name: financial_quality_results; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.financial_quality_results (
    symbol text NOT NULL,
    model_type text NOT NULL,
    quality_status text NOT NULL,
    total_score numeric,
    coverage_ratio numeric NOT NULL,
    profitability_score numeric,
    cash_flow_score numeric,
    balance_sheet_score numeric,
    growth_score numeric,
    reasons jsonb DEFAULT '[]'::jsonb NOT NULL,
    calculation_details jsonb DEFAULT '{}'::jsonb NOT NULL,
    calculated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: institution_extractions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.institution_extractions (
    disclosure_id uuid NOT NULL,
    parser_version text NOT NULL,
    candidate_count integer NOT NULL,
    processed_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: instruments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.instruments (
    symbol text NOT NULL,
    name text NOT NULL,
    sector text,
    strategy_type text,
    active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: market_screen_results; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.market_screen_results (
    symbol text NOT NULL,
    screen_date date NOT NULL,
    sector text NOT NULL,
    current_price numeric NOT NULL,
    pe numeric NOT NULL,
    pb numeric,
    market_cap numeric NOT NULL,
    initial_score numeric NOT NULL,
    status text NOT NULL,
    source_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    board text DEFAULT '待板块映射'::text NOT NULL
);


--
-- Name: monthly_snapshots; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.monthly_snapshots (
    symbol text NOT NULL,
    snapshot_month text NOT NULL,
    current_price numeric NOT NULL,
    fair_value numeric,
    safety_margin numeric,
    valuation_status text NOT NULL,
    build_signal text NOT NULL,
    target_weight numeric DEFAULT 0 NOT NULL,
    revenue_yoy numeric,
    net_income_yoy numeric,
    roe numeric,
    data_status text NOT NULL,
    snapshot_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT monthly_snapshots_snapshot_month_check CHECK ((snapshot_month ~ '^[0-9]{4}-[0-9]{2}$'::text))
);


--
-- Name: official_disclosures; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.official_disclosures (
    disclosure_id uuid NOT NULL,
    symbol text NOT NULL,
    report_period text NOT NULL,
    report_kind text NOT NULL,
    title text NOT NULL,
    source_name text NOT NULL,
    source_url text NOT NULL,
    published_at timestamp with time zone NOT NULL,
    sha256 text NOT NULL,
    local_path text NOT NULL,
    fetched_at timestamp with time zone DEFAULT now() NOT NULL,
    review_status text DEFAULT 'pending'::text NOT NULL,
    report_assurance text DEFAULT 'statutory_report_assurance_not_classified'::text NOT NULL,
    extraction_status text DEFAULT 'pending'::text NOT NULL,
    extraction_claimed_at timestamp with time zone,
    extraction_error text,
    extraction_attempts integer DEFAULT 0 NOT NULL,
    extraction_parser_version text DEFAULT 'filing-extract-v2'::text NOT NULL,
    archive_status text DEFAULT 'server_resident'::text NOT NULL,
    archive_uri text,
    archived_at timestamp with time zone,
    archive_manifest_sha256 text,
    CONSTRAINT official_disclosures_archive_status_check CHECK ((archive_status = ANY (ARRAY['server_resident'::text, 'cold_archived'::text]))),
    CONSTRAINT official_disclosures_extraction_status_check CHECK ((extraction_status = ANY (ARRAY['pending'::text, 'processing'::text, 'extracted'::text, 'no_candidates'::text, 'failed'::text]))),
    CONSTRAINT official_disclosures_review_status_check CHECK ((review_status = ANY (ARRAY['pending'::text, 'verified'::text, 'rejected'::text])))
);


--
-- Name: raw_documents; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.raw_documents (
    document_id uuid NOT NULL,
    source_name text NOT NULL,
    source_url text NOT NULL,
    published_at timestamp with time zone,
    fetched_at timestamp with time zone NOT NULL,
    parser_version text NOT NULL,
    sha256 text NOT NULL,
    local_path text,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL
);


--
-- Name: task_runs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.task_runs (
    run_id uuid NOT NULL,
    task_name text NOT NULL,
    started_at timestamp with time zone NOT NULL,
    finished_at timestamp with time zone,
    status text NOT NULL,
    details jsonb DEFAULT '{}'::jsonb NOT NULL,
    CONSTRAINT task_runs_status_check CHECK ((status = ANY (ARRAY['running'::text, 'succeeded'::text, 'failed'::text])))
);


--
-- Name: valuation_results; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.valuation_results (
    symbol text NOT NULL,
    current_price numeric,
    fair_value numeric,
    safety_margin numeric,
    valuation_status text NOT NULL,
    build_signal text NOT NULL,
    target_weight numeric DEFAULT 0 NOT NULL,
    data_status text NOT NULL,
    calculated_at timestamp with time zone DEFAULT now() NOT NULL,
    calculation_details jsonb DEFAULT '{}'::jsonb NOT NULL
);


--
-- Name: backup_audits backup_audits_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.backup_audits
    ADD CONSTRAINT backup_audits_pkey PRIMARY KEY (backup_id);


--
-- Name: candidate_tracking_observations candidate_tracking_observations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.candidate_tracking_observations
    ADD CONSTRAINT candidate_tracking_observations_pkey PRIMARY KEY (run_id, symbol);


--
-- Name: data_points data_points_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.data_points
    ADD CONSTRAINT data_points_pkey PRIMARY KEY (data_point_id);


--
-- Name: filing_candidates filing_candidates_disclosure_id_field_name_page_number_sour_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.filing_candidates
    ADD CONSTRAINT filing_candidates_disclosure_id_field_name_page_number_sour_key UNIQUE (disclosure_id, field_name, page_number, source_label);


--
-- Name: filing_candidates filing_candidates_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.filing_candidates
    ADD CONSTRAINT filing_candidates_pkey PRIMARY KEY (candidate_id);


--
-- Name: financial_enrichment_queue financial_enrichment_queue_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.financial_enrichment_queue
    ADD CONSTRAINT financial_enrichment_queue_pkey PRIMARY KEY (symbol);


--
-- Name: financial_quality_results financial_quality_results_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.financial_quality_results
    ADD CONSTRAINT financial_quality_results_pkey PRIMARY KEY (symbol);


--
-- Name: institution_extractions institution_extractions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.institution_extractions
    ADD CONSTRAINT institution_extractions_pkey PRIMARY KEY (disclosure_id, parser_version);


--
-- Name: instruments instruments_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.instruments
    ADD CONSTRAINT instruments_pkey PRIMARY KEY (symbol);


--
-- Name: market_screen_results market_screen_results_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.market_screen_results
    ADD CONSTRAINT market_screen_results_pkey PRIMARY KEY (symbol, screen_date);


--
-- Name: monthly_snapshots monthly_snapshots_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.monthly_snapshots
    ADD CONSTRAINT monthly_snapshots_pkey PRIMARY KEY (symbol, snapshot_month);


--
-- Name: official_disclosures official_disclosures_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.official_disclosures
    ADD CONSTRAINT official_disclosures_pkey PRIMARY KEY (disclosure_id);


--
-- Name: official_disclosures official_disclosures_symbol_sha256_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.official_disclosures
    ADD CONSTRAINT official_disclosures_symbol_sha256_key UNIQUE (symbol, sha256);


--
-- Name: raw_documents raw_documents_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.raw_documents
    ADD CONSTRAINT raw_documents_pkey PRIMARY KEY (document_id);


--
-- Name: raw_documents raw_documents_sha256_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.raw_documents
    ADD CONSTRAINT raw_documents_sha256_key UNIQUE (sha256);


--
-- Name: task_runs task_runs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_runs
    ADD CONSTRAINT task_runs_pkey PRIMARY KEY (run_id);


--
-- Name: valuation_results valuation_results_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.valuation_results
    ADD CONSTRAINT valuation_results_pkey PRIMARY KEY (symbol);


--
-- Name: candidate_tracking_latest; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX candidate_tracking_latest ON public.candidate_tracking_observations USING btree (symbol, quote_as_of DESC, created_at DESC);


--
-- Name: data_points_lookup; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX data_points_lookup ON public.data_points USING btree (symbol, field_name, period_label, created_at DESC);


--
-- Name: filing_candidates_review; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX filing_candidates_review ON public.filing_candidates USING btree (created_at DESC, disclosure_id);


--
-- Name: financial_enrichment_queue_next; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX financial_enrichment_queue_next ON public.financial_enrichment_queue USING btree (status, priority_score DESC, updated_at);


--
-- Name: financial_quality_results_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX financial_quality_results_status ON public.financial_quality_results USING btree (quality_status, total_score DESC NULLS LAST);


--
-- Name: market_screen_results_lookup; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX market_screen_results_lookup ON public.market_screen_results USING btree (screen_date DESC, initial_score DESC);


--
-- Name: official_disclosures_extraction_queue; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX official_disclosures_extraction_queue ON public.official_disclosures USING btree (extraction_status, extraction_claimed_at, published_at DESC);


--
-- Name: official_disclosures_lookup; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX official_disclosures_lookup ON public.official_disclosures USING btree (symbol, report_period, report_kind, published_at DESC);


--
-- Name: official_disclosures_residency_lookup; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX official_disclosures_residency_lookup ON public.official_disclosures USING btree (archive_status, extraction_status, fetched_at);


--
-- Name: candidate_tracking_observations candidate_tracking_observations_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.candidate_tracking_observations
    ADD CONSTRAINT candidate_tracking_observations_run_id_fkey FOREIGN KEY (run_id) REFERENCES public.task_runs(run_id);


--
-- Name: candidate_tracking_observations candidate_tracking_observations_source_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.candidate_tracking_observations
    ADD CONSTRAINT candidate_tracking_observations_source_id_fkey FOREIGN KEY (source_id) REFERENCES public.raw_documents(document_id);


--
-- Name: candidate_tracking_observations candidate_tracking_observations_symbol_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.candidate_tracking_observations
    ADD CONSTRAINT candidate_tracking_observations_symbol_fkey FOREIGN KEY (symbol) REFERENCES public.instruments(symbol);


--
-- Name: data_points data_points_source_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.data_points
    ADD CONSTRAINT data_points_source_id_fkey FOREIGN KEY (source_id) REFERENCES public.raw_documents(document_id);


--
-- Name: data_points data_points_symbol_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.data_points
    ADD CONSTRAINT data_points_symbol_fkey FOREIGN KEY (symbol) REFERENCES public.instruments(symbol);


--
-- Name: filing_candidates filing_candidates_disclosure_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.filing_candidates
    ADD CONSTRAINT filing_candidates_disclosure_id_fkey FOREIGN KEY (disclosure_id) REFERENCES public.official_disclosures(disclosure_id);


--
-- Name: financial_enrichment_queue financial_enrichment_queue_symbol_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.financial_enrichment_queue
    ADD CONSTRAINT financial_enrichment_queue_symbol_fkey FOREIGN KEY (symbol) REFERENCES public.instruments(symbol);


--
-- Name: financial_quality_results financial_quality_results_symbol_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.financial_quality_results
    ADD CONSTRAINT financial_quality_results_symbol_fkey FOREIGN KEY (symbol) REFERENCES public.instruments(symbol);


--
-- Name: institution_extractions institution_extractions_disclosure_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.institution_extractions
    ADD CONSTRAINT institution_extractions_disclosure_id_fkey FOREIGN KEY (disclosure_id) REFERENCES public.official_disclosures(disclosure_id);


--
-- Name: market_screen_results market_screen_results_source_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.market_screen_results
    ADD CONSTRAINT market_screen_results_source_id_fkey FOREIGN KEY (source_id) REFERENCES public.raw_documents(document_id);


--
-- Name: market_screen_results market_screen_results_symbol_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.market_screen_results
    ADD CONSTRAINT market_screen_results_symbol_fkey FOREIGN KEY (symbol) REFERENCES public.instruments(symbol);


--
-- Name: monthly_snapshots monthly_snapshots_symbol_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.monthly_snapshots
    ADD CONSTRAINT monthly_snapshots_symbol_fkey FOREIGN KEY (symbol) REFERENCES public.instruments(symbol);


--
-- Name: official_disclosures official_disclosures_symbol_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.official_disclosures
    ADD CONSTRAINT official_disclosures_symbol_fkey FOREIGN KEY (symbol) REFERENCES public.instruments(symbol);


--
-- Name: valuation_results valuation_results_symbol_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.valuation_results
    ADD CONSTRAINT valuation_results_symbol_fkey FOREIGN KEY (symbol) REFERENCES public.instruments(symbol);


--
-- PostgreSQL database dump complete
--

\unrestrict Cz1SIQadFSaDAyAKLo18jaIbao9P3j0vtp9UHaQwNMSVDJQJ3jZPt8uSlF5NrUl
