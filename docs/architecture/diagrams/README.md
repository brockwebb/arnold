# Arnold System Architecture Diagrams

> **Purpose**: Visual system views for presentations and documentation.
> 
> **Render**: Use Mermaid Live Editor (https://mermaid.live) or GitHub's native rendering.

---

## Diagram Index

| Diagram | View | Purpose |
|---------|------|---------|
| [sv0-system-context.mermaid](./sv0-system-context.mermaid) | SV-0 | High-level system boundaries |
| [sv1-component-architecture.mermaid](./sv1-component-architecture.mermaid) | SV-1 | Internal components and tools |
| [data-flow.mermaid](./data-flow.mermaid) | OV-2 | Data movement through system |
| [intelligence-stack.mermaid](./intelligence-stack.mermaid) | Conceptual | Layered intelligence model |

---

## SV-0: System Context

**Slide Title**: "Arnold - AI Fitness Coach"

**Key Points**:
- Arnold is the black box in the middle
- External data sources flow in (Ultrahuman, Polar, Apple Health, manual)
- Outputs flow out (Athlete guidance, Reports, Decision traces)
- Inside: Claude orchestrates MCP tools against dual storage

**Talking Points**:
- "Arnold integrates data from multiple wearables and health sources"
- "Claude Desktop serves as the reasoning engine - MCPs are specialist tools"
- "Dual storage: Neo4j for relationships, Postgres for facts"

---

## SV-1: Component Architecture

**Slide Title**: "Inside Arnold"

**Key Points**:
- **Orchestration**: Claude Desktop - the "head coach"
- **MCP Tools**: Specialist servers for training, memory, journal, analytics, profile
- **Data Layer**: Follows ADR-001 separation
  - Neo4j = "Right Brain" (relationships, knowledge)
  - Postgres = "Left Brain" (facts, time series)

**Talking Points**:
- "5 MCP servers, each with focused responsibility"
- "4,242 exercises in knowledge graph with muscle targeting"
- "165 strength sessions migrated to Postgres analytics layer"

**Numbers to cite**:
- 4,242 exercises
- 165 strength sessions, 2,482 sets
- 3,600+ biometric readings
- 114 races (18 years history)

---

## Data Flow

**Slide Title**: "How Data Moves"

**Key Points**:
- Left to right flow: Sources → Ingest → Storage → Intelligence → Output
- `sync_pipeline.py` orchestrates ingestion
- Analytics computes metrics, Memory loads context
- Claude synthesizes into decisions

**Talking Points**:
- "Daily automated sync from Ultrahuman API"
- "Analytics layer computes ACWR, readiness, pattern gaps"
- "Every decision creates an audit trail (ADR-004)"

---

## Intelligence Stack

**Slide Title**: "From Data to Decisions"

**Key Points**:
- **Layer 1**: Raw data (biometrics, training, subjective)
- **Layer 2**: Computed metrics (readiness, load, gaps, progression)
- **Layer 3**: Coach intelligence (context, policies, conflict resolution)
- **Layer 4**: Output (coach brief, athlete brief, decision trace)

**Talking Points**:
- "Raw data becomes metrics through evidence-based calculations"
- "Coach applies policies grounded in peer-reviewed research"
- "When signals conflict (HRV says rest, pattern gap says train), Coach resolves"
- "Two outputs: detailed Coach Brief, compact Athlete Brief"

---

## Presentation Sequence

**3-Slide Version**:
1. SV-0: "What is Arnold?" - system boundaries, inputs/outputs
2. Intelligence Stack: "How it thinks" - layered intelligence
3. SV-1: "Inside the box" - components and tools

**1-Slide Version**:
- Use SV-0 only, expand verbally

**Deep Dive (5+ slides)**:
1. SV-0: System context
2. Data Flow: How data moves
3. Intelligence Stack: Layered thinking
4. SV-1: Component details
5. Future: Decision traces, functional lenses, athlete brief

---

## Rendering Notes

**GitHub**: Mermaid renders automatically in `.md` files with code blocks.

**Slides**: 
1. Go to https://mermaid.live
2. Paste diagram content
3. Export as PNG/SVG
4. Insert into slides

**VS Code**: Install "Mermaid Preview" extension for live rendering.
