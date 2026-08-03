# C.R.A.I.L.S. Platform

**Chaos · Reliability · Automation · Innovation · Learning · Stress-Testing**

A production-grade, private-cloud SRE reference environment built to simulate real enterprise infrastructure patterns across isolated staging and production environments.

> **Author:** Biswadip Majumdar — Lead SRE  
> **LinkedIn:** [linkedin.com/in/biswadipmajumdar](https://linkedin.com/in/biswadipmajumdar)  
> **GitHub:** [github.com/warrator](https://github.com/warrator)

---

## Platform Overview

The C.R.A.I.L.S. Platform runs on a **nested hypervisor stack**:

```
Windows 11 (HP Spectre)
  └── VMware Workstation Pro (Type-2 hypervisor)
        └── Proxmox VE 9.2 (Type-1, nested)
              ├── crails-k3s-master-node01   — K3s Control Plane, DNS (dnsmasq), Traefik, MetalLB, Jenkins
              ├── crails-k3s-worker-node02   — K3s Worker, prod PostgreSQL replica (pglogical), observability
              └── crails-hybrid-worker-node03 — K3s Worker, standalone PostgreSQL primary, Redis, chaos tooling
```

**Cluster:** 3-node Ubuntu 22.04 k3s cluster (5 vCPU / 4 GB RAM per node)  
**Environments:** Staging (`staging` namespace) + Production (`production` namespace)  
**Current phase:** Phase 2 — nested Proxmox 3-node design with two-way PostgreSQL logical replication (pglogical)

---

## Repository Structure

```
crails/
├── crails-platform-docs/
│   ├── docs/
│   │   ├── HLD/                    High-Level Design — architecture, goals, topology
│   │   ├── LLD/                    Low-Level Design — VM specs, network, k3s config, service layout
│   │   ├── SLO-SLI/                SLO & SLI definitions + error budget policy (Google SRE principles)
│   │   ├── runbooks/                Incident runbooks — PostgreSQL failure, node loss, Redis OOM
│   │   └── chaos-engineering/       Chaos scenarios, blast radius analysis, recovery playbooks
│   └── dashboards/
│       └── CRAILS_Platform_Status_Dashboard.xlsx   Live platform status tracker (40/46 components running)
└── sre-tools/
    ├── criticality_engine.py       Auto-tags services by tier (traffic, fan-in, incident history)
    ├── blast_radius.py             Computes downstream impact of a service failure
    ├── circuit_breaker_sim.py      CLOSED/OPEN/HALF_OPEN state machine + flaky-service demo
    ├── error_budget_tracker.py     Red Mode release gating from SLO burn rate
    ├── examples/                   Sample YAML configs for each tool
    └── tests/                      25 unit tests (pytest)
```

All documentation lives in [`crails-platform-docs/`](https://github.com/warrator/crails/tree/main/crails-platform-docs).
The SRE automation toolkit lives in [`sre-tools/`](https://github.com/warrator/crails/tree/main/sre-tools).

---

## Key Technical Highlights

| Area | Implementation |
|------|---------------|
| **Orchestration** | k3s (lightweight Kubernetes) on 3-node Proxmox cluster |
| **Ingress** | Traefik via MetalLB VIP |
| **CI/CD** | Jenkins (staging + production build pipelines) + ArgoCD (production GitOps) |
| **Database** | PostgreSQL standalone primary (hybrid node) + StatefulSet replica (worker-node02) via pglogical two-way logical replication |
| **Cache** | Redis (standalone + in-cluster, hybrid node) |
| **Observability** | Prometheus + Grafana (redeploying on new cluster) |
| **Chaos tooling** | Gremlin / Chaos Mesh (hybrid node) |
| **DNS** | dnsmasq internal DNS on master node |
| **Service** | Password Manager Backend (Python FastAPI) — staging + production |

---

## SRE-Grade Python Toolkit

Standalone, tested implementations of the reliability patterns used across the platform — runnable as CLI tools or imported as libraries, and designed to plug into the Istio, Prometheus, and ArgoCD layers documented above.

| Script | What it does |
|---|---|
| [`criticality_engine.py`](sre-tools/criticality_engine.py) | Scores services on traffic share, dependency fan-in, and incident history; maps to tier-1/2/3 with SLA targets; emits `kubectl`-ready annotation patches |
| [`blast_radius.py`](sre-tools/blast_radius.py) | Walks a service dependency graph to compute every service transitively impacted by a failure, with hop-distance and severity scoring |
| [`circuit_breaker_sim.py`](sre-tools/circuit_breaker_sim.py) | A from-scratch CLOSED → OPEN → HALF_OPEN state machine matching the mesh-level pattern Istio enforces; includes a `--demo` mode |
| [`error_budget_tracker.py`](sre-tools/error_budget_tracker.py) | Computes error-budget burn rate and applies the Red Mode release-gating policy (GREEN/YELLOW/RED/INCIDENT); works against mock data or live Prometheus |

25 unit tests, all passing (`python -m pytest tests/ -v`). Full usage examples in [`sre-tools/README.md`](sre-tools/README.md).

---

| SLO | Target | Window |
|-----|--------|--------|
| Availability | 99.0% | Rolling 30 days |
| Latency (p99) | < 500ms | Rolling 5 minutes |
| Error Rate | < 1% | Rolling 1 hour |
| PostgreSQL Availability | 99.0% | Rolling 30 days |
| Redis Availability | 99.0% | Rolling 30 days |

Error budget policy: deploy freeze when budget drops below 25%; incident declared at 0%.

---

## Documentation Index

| Document | Description |
|----------|-------------|
| [HLD](crails-platform-docs/docs/HLD/CRAILS_Platform_HLD.docx) | Architecture overview, platform goals, environment strategy, technology decisions |
| [LLD](crails-platform-docs/docs/LLD/CRAILS_Platform_LLD.docx) | VM specs, network topology, k3s config, storage, service-level configuration |
| [SLO/SLI](crails-platform-docs/docs/SLO-SLI/CRAILS_Platform_SLO_SLI.docx) | SLI definitions, SLO targets, error budgets, alerting thresholds, Grafana dashboard specs |
| [Runbook](crails-platform-docs/docs/runbooks/CRAILS_Platform_Runbook.docx) | Incident response — PostgreSQL failure + replica promotion, node loss, Jenkins PVC recovery, Redis OOM |
| [Chaos Engineering](crails-platform-docs/docs/chaos-engineering/CRAILS_Platform_Chaos_Engineering.docx) | Failure scenarios, blast radius analysis, MTTR targets, recovery procedures |
| [Status Dashboard](crails-platform-docs/dashboards/CRAILS_Platform_Status_Dashboard.xlsx) | Live component tracker — 40/46 components running across staging + production |

---

## Platform Status

| Component | Status |
|-----------|--------|
| Total components tracked | 46 |
| Running | ✅ 40 |
| Planned / In Progress | 📋 6 |
| Environments | Staging + Production |
| Phase | Phase 2 (3-node nested Proxmox) |
