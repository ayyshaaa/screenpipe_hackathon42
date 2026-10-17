# THROUGHT pipeline. Run `make help` from the repo root.
#
#   make pipeline FROM=2026-09-07 TO=2026-10-06      # fake data, the whole month (7 Sep -> 6 Oct)
#   make pipeline FROM=2026-09-14 TO=2026-09-27      # fake data, 2 weeks
#   make pipeline FROM=2026-09-07                    # fake data, 7 Sep -> most recent data
#   make pipeline FAKE=0 FROM=2026-10-01             # real screenpipe on :3030
#   make review                                      # then confirm/reject, Save, Ctrl+C
#   make export repetition desk

ROOT      := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
EVENT     := $(ROOT)/event
VENV      := $(ROOT)/.venv
PY        := $(VENV)/bin/python
STARTER   ?= $(ROOT)/hackathon-starter

# FAKE=1: synthetic data + answer key, FAKE=0: real screenpipe
FAKE      ?= 1
FAKE_PORT ?= 3031
ifeq ($(FAKE),1)
URL       ?= http://localhost:$(FAKE_PORT)
SCORE     := --score
TRUTH     := --show-truth
else
URL       ?= http://localhost:3030
SCORE     :=
TRUTH     :=
endif

# UTC range. FROM empty = all history; TO empty = most recent data; TO needs FROM.
# A bare date is a whole day: FROM=2026-09-07 TO=2026-09-13 covers both days fully.
FROM      ?=
TO        ?=
TYPES     ?= ocr,accessibility
# MODEL=hashing needs no download
MODEL     ?= VTXAI/VTX-JEV-2
# empty = picked from MODEL (0.9 JEV-2, 0.6 hashing, see event/common.py); set it to override
THRESHOLD ?=
# a task must repeat on at least MIN_DAYS different days to count as repetitive
MIN_DAYS  ?= 3
LLM       ?= qwen3:4b-instruct
REVIEW_PORT ?= 4300

THR   := $(if $(THRESHOLD),--threshold $(THRESHOLD))
RANGE := $(if $(FROM),--from $(FROM)) $(if $(TO),--to $(TO))
PIDFILE := $(EVENT)/.fake_screenpipe.pid
export HF_HUB_OFFLINE ?= 1

.PHONY: help install story fake-up fake-down ingest label embed sweep tasks describe pipeline \
        review export repetition desk check clean

help:
	@echo "THROUGHT — make targets (variables: FROM, TO, FAKE, MODEL, THRESHOLD, MIN_DAYS, URL, TYPES)"
	@echo "  install      create .venv and install requirements.txt"
	@echo "  pipeline     ingest -> (label) -> embed -> tasks"
	@echo "               whole month: make pipeline FROM=2026-09-07 TO=2026-10-06"
	@echo "               2 weeks:     make pipeline FROM=2026-09-14 TO=2026-09-27"
	@echo "  ingest       step 1  screenpipe -> trail.db (only the FROM/TO range is kept)"
	@echo "  label        step 1b answer key per session (FAKE=1 only)"
	@echo "  embed        step 2  sessions -> embeddings.npz"
	@echo "  sweep        step 2b precision/recall per threshold (FAKE=1 only)"
	@echo "  tasks        step 3  -> throught_runs.json"
	@echo "  describe     step 4  local LLM names the tasks (optional, needs ollama)"
	@echo "  review       step 5  review page on :$(REVIEW_PORT) (Save, then Ctrl+C)"
	@echo "  export       step 6  -> starter_records.json, desk_records.json, desk_draft.json"
	@echo "  repetition   step 7  bun run repetition in hackathon-starter"
	@echo "  desk         step 8  bun start --draft in hackathon-starter (:4242)"
	@echo "  check        end-to-end test on the synthetic data"
	@echo "  fake-up / fake-down   start / stop the fake screenpipe in the background"
	@echo "  clean        delete trail.db and every generated output"

install:
	test -x $(PY) || python3 -m venv $(VENV)
	$(PY) -m pip install -r $(ROOT)/requirements.txt

# ---------- synthetic data ----------

story:
	cd $(EVENT) && $(PY) fake_story.py

fake-up:
	@if [ -f $(PIDFILE) ] && kill -0 $$(cat $(PIDFILE)) 2>/dev/null; then \
	  echo "fake screenpipe already running (pid $$(cat $(PIDFILE)))"; \
	else \
	  (cd $(EVENT) && exec $(PY) fake_screenpipe.py serve --port $(FAKE_PORT) > fake_screenpipe.log 2>&1) & \
	  echo $$! > $(PIDFILE); \
	  for i in $$(seq 30); do \
	    $(PY) -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:$(FAKE_PORT)/health', timeout=1)" 2>/dev/null && break; \
	    sleep 0.5; \
	  done; \
	  echo "fake screenpipe on :$(FAKE_PORT) (pid $$(cat $(PIDFILE)), log event/fake_screenpipe.log)"; \
	fi

fake-down:
	@if [ -f $(PIDFILE) ]; then kill $$(cat $(PIDFILE)) 2>/dev/null || true; rm -f $(PIDFILE); echo "fake screenpipe stopped"; fi

# ---------- pipeline ----------

ingest:
ifeq ($(FAKE),1)
	@$(MAKE) --no-print-directory fake-up
endif
	cd $(EVENT) && $(PY) ingest.py --url $(URL) $(RANGE) --types $(TYPES) --once

label:
ifeq ($(FAKE),1)
	cd $(EVENT) && $(PY) label_sessions.py
else
	@echo "label: skipped (real data has no answer key)"
endif

embed:
	cd $(EVENT) && $(PY) embed.py --model $(MODEL)

sweep:
	cd $(EVENT) && $(PY) find_tasks.py --sweep

tasks:
	cd $(EVENT) && $(PY) find_tasks.py $(THR) --min-days $(MIN_DAYS) $(SCORE)

describe:
	cd $(EVENT) && $(PY) describe_tasks.py --model $(LLM)

pipeline:
	$(MAKE) --no-print-directory ingest
	$(MAKE) --no-print-directory label
	$(MAKE) --no-print-directory embed
	$(MAKE) --no-print-directory tasks
ifeq ($(FAKE),1)
	@$(MAKE) --no-print-directory fake-down
endif
	@echo "next: make review  (then make export repetition desk)"

review:
	cd $(EVENT) && $(PY) review.py $(TRUTH) --port $(REVIEW_PORT)

export:
	cd $(EVENT) && $(PY) export_starter.py

repetition:
	cd $(STARTER) && bun run repetition --input $(EVENT)/starter_records.json

desk:
	cd $(STARTER) && bun start --draft $(EVENT)/desk_draft.json

check:
	cd $(EVENT) && $(PY) check_pipeline.py --model $(MODEL) $(THR)

clean:
	cd $(EVENT) && rm -f trail.db embeddings.npz throught_runs.json task_descriptions.json \
	  reviewed_runs.json review_state.json starter_records.json desk_records.json desk_draft.json \
	  fake_screenpipe.log
