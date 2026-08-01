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
crails-platform/
├── docs/
│   ├── HLD/                        High-Level Design — architecture, goals, topology
│   ├── LLD/                        Low-Level Design — VM specs, network, k3s config, service layout
│   ├── SLO-SLI/                    SLO & SLI definitions + error budget policy (Google SRE principles)
│   ├── runbooks/                   Incident runbooks — PostgreSQL failure, node loss, Redis OOM
│   └── chaos-engineering/          Chaos scenarios, blast radius analysis, recovery playbooks
└── dashboards/
    └── CRAILS_Platform_Status_Dashboard.xlsx   Live platform status tracker (40/46 components running)
```

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

## SLO Targets (Production)

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
| [HLD](docs/HLD/CRAILS_Platform_HLD.docx) | Architecture overview, platform goals, environment strategy, technology decisions |
| [LLD](docs/LLD/CRAILS_Platform_LLD.docx) | VM specs, network topology, k3s config, storage, service-level configuration |
| [SLO/SLI](docs/SLO-SLI/CRAILS_Platform_SLO_SLI.docx) | SLI definitions, SLO targets, error budgets, alerting thresholds, Grafana dashboard specs |
| [Runbook](docs/runbooks/CRAILS_Platform_Runbook.docx) | Incident response — PostgreSQL failure + replica promotion, node loss, Jenkins PVC recovery, Redis OOM |
| [Chaos Engineering](docs/chaos-engineering/CRAILS_Platform_Chaos_Engineering.docx) | Failure scenarios, blast radius analysis, MTTR targets, recovery procedures |
| [Status Dashboard](dashboards/CRAILS_Platform_Status_Dashboard.xlsx) | Live component tracker — 40/46 components running across staging + production |

---

## Platform Status

| Component | Status |
|-----------|--------|
| Total components tracked | 46 |
| Running | ✅ 40 |
| Planned / In Progress | 📋 6 |
| Environments | Staging + Production |
| Phase | Phase 2 (3-node nested Proxmox) |
