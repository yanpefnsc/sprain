--
-- PostgreSQL database dump
--

-- Dumped from database version 17.5 (Debian 17.5-1.pgdg110+1)
-- Dumped by pg_dump version 17.5 (Debian 17.5-1.pgdg110+1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
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
-- Name: corredor_sp_araraquara; Type: TABLE; Schema: public; Owner: enchentes
--

CREATE TABLE public.corredor_sp_araraquara (
    id_trecho integer NOT NULL,
    name character varying(255),
    highway character varying(50),
    length double precision,
    geometry public.geometry(LineString,31983)
);


ALTER TABLE public.corredor_sp_araraquara OWNER TO enchentes;

--
-- Name: corredor_sp_araraquara_id_trecho_seq; Type: SEQUENCE; Schema: public; Owner: enchentes
--

CREATE SEQUENCE public.corredor_sp_araraquara_id_trecho_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.corredor_sp_araraquara_id_trecho_seq OWNER TO enchentes;

--
-- Name: corredor_sp_araraquara_id_trecho_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: enchentes
--

ALTER SEQUENCE public.corredor_sp_araraquara_id_trecho_seq OWNED BY public.corredor_sp_araraquara.id_trecho;


--
-- Name: corredor_sp_araraquara id_trecho; Type: DEFAULT; Schema: public; Owner: enchentes
--

ALTER TABLE ONLY public.corredor_sp_araraquara ALTER COLUMN id_trecho SET DEFAULT nextval('public.corredor_sp_araraquara_id_trecho_seq'::regclass);


--
-- Data for Name: corredor_sp_araraquara; Type: TABLE DATA; Schema: public; Owner: enchentes
--

COPY public.corredor_sp_araraquara (id_trecho, name, highway, length, geometry) FROM stdin;
1	Rod. Washington Luis (SP-310) - Araraquara a Sao Carlos	motorway	38320.85098694095	0102000020EF7C0000020000008C40198500F50441C9A1D493C8F05C415CCF0268FC9C0841BF6DA79A70D95C41
2	Rod. Washington Luis (SP-310) - Sao Carlos a Rio Claro	motorway	55592.00375038128	0102000020EF7C0000020000005CCF0268FC9C0841BF6DA79A70D95C4124F6E4374CED0C4189B4DAD987AF5C41
3	Rod. Washington Luis (SP-310) - Rio Claro a Limeira	motorway	23452.384203579295	0102000020EF7C00000200000024F6E4374CED0C4189B4DAD987AF5C417B3268D59AE50E411CDB7B8DE99E5C41
4	Rod. Anhanguera / Bandeirantes (SP-330/348) - Limeira a Campinas	motorway	51519.85510711991	0102000020EF7C0000020000007B3268D59AE50E411CDB7B8DE99E5C4191E3549F129F11413562D2778B7A5C41
5	Rod. dos Bandeirantes (SP-348) - Campinas a Jundiai	motorway	35825.65254115777	0102000020EF7C00000200000091E3549F129F11413562D2778B7A5C4149EA499DD9BD1241B65A6FAE7F5C5C41
6	Rod. dos Bandeirantes (SP-348) - Jundiai a Sao Paulo Marginal	motorway	40254.57795584445	0102000020EF7C00000200000049EA499DD9BD1241B65A6FAE7F5C5C4157B778E495CC134170A98C0704395C41
\.


--
-- Name: corredor_sp_araraquara_id_trecho_seq; Type: SEQUENCE SET; Schema: public; Owner: enchentes
--

SELECT pg_catalog.setval('public.corredor_sp_araraquara_id_trecho_seq', 6, true);


--
-- Name: corredor_sp_araraquara corredor_sp_araraquara_pkey; Type: CONSTRAINT; Schema: public; Owner: enchentes
--

ALTER TABLE ONLY public.corredor_sp_araraquara
    ADD CONSTRAINT corredor_sp_araraquara_pkey PRIMARY KEY (id_trecho);


--
-- Name: idx_corredor_geom; Type: INDEX; Schema: public; Owner: enchentes
--

CREATE INDEX idx_corredor_geom ON public.corredor_sp_araraquara USING gist (geometry);


--
-- PostgreSQL database dump complete
--

