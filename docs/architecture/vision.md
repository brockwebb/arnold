# Vision: The Digital Twin

> **Last Updated**: January 8, 2026

Arnold is the first implementation of a broader vision: **personal health sovereignty through data ownership and AI-augmented analysis.**

---

## The Problem

Everyday people get 15 minutes with a doctor, twice a year. Doctors are specialists with discipline-specific training, knowledge gaps, and anchoring bias from what they learned in school and residency. No single human can see the complete picture of another human's health across all domains and time.

Meanwhile, individuals generate vast amounts of health data—workouts, sleep, heart rate, nutrition, lab work, symptoms, medications—scattered across apps, devices, and medical records they don't control.

---

## The Vision

A **Digital Twin** is a comprehensive, longitudinal model of a person that:

1. **Aggregates all personal health data** — training, biometrics, medical records, lab work, nutrition, sleep, symptoms, even thoughts and reflections
2. **Owns the data** — privacy-first, user-controlled, portable
3. **Enables pattern detection** — AI agents find correlations humans miss across time and domains
4. **Stays current with research** — deep research agents crawl latest literature, not anchored to outdated training
5. **Augments (not replaces) professionals** — better informed conversations with doctors, coaches, therapists

---

## The Team Model

Claude orchestrates specialist agents, each with domain expertise:

| Agent | Domain | Role |
|-------|--------|------|
| **Coach** | Fitness/Training | Programming, periodization, exercise selection |
| **Doc** | Medical/Health | Symptom tracking, medication interactions, lab interpretation, rehab protocols |
| **Analyst** | Data Science | Trends, correlations, reports, visualizations |
| **Researcher** | Literature | Latest evidence, protocol recommendations, myth-busting |
| **Scribe** | Documentation | Logging, journaling, reflection capture |

Arnold (Coach) is the first specialist. Others follow the same pattern: MCP tools + Neo4j storage + Claude reasoning.

---

## Data Sources (Current)

| Source | Data Type | Method | Status |
|--------|-----------|--------|--------|
| Ultrahuman API | Sleep, HRV, resting HR, temp, recovery | Automated daily | ✅ Live |
| Polar Export | HR sessions, TRIMP, zones | Manual weekly | ✅ Live |
| Apple Health | Medical records, labs, BP, meds | Manual monthly | ✅ Live |
| Race History | Historical performance (114 races, 2005-2023) | One-time import | ✅ Done |
| Neo4j Workouts | Training structure, exercises | Automated sync | ✅ Live |

---

## Why This Matters

This isn't about replacing doctors. It's about:

- **Better conversations** — arrive informed, ask better questions
- **Pattern detection** — "Your HRV drops 3 days before you get sick"
- **Longitudinal insight** — trends over years, not snapshots
- **Privacy** — your data, your control, your choice who sees it
- **Democratization** — elite-level analysis for everyone

Arnold proves the model works. The Digital Twin is where it's going.

---

## Core Architectural Principles

1. **Modality as Hub** — Training domains (Hip Hinge Strength, Ultra Endurance, etc.) are the central organizing concept. Everything connects through modality.

2. **Block as Fundamental Unit** — Time is organized into blocks (typically 3-4 weeks). Blocks serve goals, contain sessions, and follow periodization models.

3. **Training Level Per Modality** — An athlete can be novice at deadlift and advanced at ultrarunning simultaneously. Progression models are selected per modality.

4. **Science-Grounded** — Periodization models, progression schemes, and coaching logic are grounded in peer-reviewed exercise science.

5. **Graph-First Thinking** — Everything is relationships. Start at any node, traverse to what you need.
