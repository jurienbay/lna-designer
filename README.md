Designs MiniCircuit RF LNA's
============================

[![Code Quality Linting Suite](https://github.com/jurienbay/lna-designer/actions/workflows/lint.yml/badge.flow.svg)](https://github.com/jurienbay/lna-designer/actions/workflows/lint.yml)


Good luck, fixes welcome.

## Physical geometry of multi-stage microstrip radial stub network

```text
                  Stage 2 Radial Stub (High Freq rejection)
                         / \
                        /   \
                       /_____\
                          |  <--- λ/4 spacing line
                  Stage 1 Radial Stub (Center Freq rejection)
                         / \
                        /   \
                       /_____\
                          |
                          |  <--- Main High-Z λ/4 Feed Line (Transforms Short to Open)
                          |
RF Signal In ═════════════╩═════════════ RF Signal Out (Main 50Ω Trace)
```

## Automated Hardware Test Bench Routine Gen

```text
┌─────────────────┐       ┌─────────────────┐       ┌─────────────────┐
│     Desktop     │ USB   │ Vector Network  │ RF    │  Your Physical  │
│  Design Suite   ├──────►│ Analyzer (VNA)  ├──────►│ Manufactured PCB│
│ (Python/PyVISA) │       └─────────────────┘       └─────────────────┘
└───────┬─────────┘
        │ USB
        ▼
┌─────────────────┐ Power
│ Programmable DC │───────► [Vcc Pad]
│  Power Supply   │
└─────────────────┘
```
