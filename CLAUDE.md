# CLAUDE.md

## Goal
Convert this Tkinter weather app into a containerized FastAPI web service for a DevOps portfolio.

## Target stack
Python 3.12, FastAPI, scikit-learn, pytest, ruff, Docker, GitHub Actions.

## Off-limits files
- Never read or edit: `build/`, `dist/`, `*.pkl`, `*.png`, `*.ico`.
- Read CSVs only with `head -5`.

## Secrets
- The WeatherAPI key comes only from the env var `WEATHER_API_KEY`. Never hardcode it.

## Working rules
- Make minimal changes.
- One phase per task.
- Run tests before finishing.
- Reply with a short summary, not full diffs.
