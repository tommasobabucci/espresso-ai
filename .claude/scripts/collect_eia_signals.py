#!/usr/bin/env python3
"""
espresso·ai — EIA Energy Signal Collector
Queries the US Energy Information Administration API v2 (free, requires free API key)
for energy data relevant to AI infrastructure scaling. Detects trends in electricity
generation, renewable capacity, and grid utilization in AI-hub states.

Generates ENERGY-lever signals from time-series trend analysis and appends them
to research_db/raw/ in JSONL format.

Usage:
    python .claude/scripts/collect_eia_signals.py --cadence weekly [--days-back 7] [--dry-run]
"""

import json
import uuid
import hashlib
import argparse
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(".env/.env")
except ImportError:
    pass

import os
import requests

# ─── Configuration ───────────────────────────────────────────────────────────

EIA_API_BASE = "https://api.eia.gov/v2"
AGENT_ID = "eia-energy-collector"
SCHEMA_VERSION = "1.0"
SOURCE_NAME = "government_statistics"

# ─── AI-Hub States ───────────────────────────────────────────────────────────
# States with the highest concentration of data center capacity.
# Virginia alone hosts ~70% of US data center capacity (Loudoun County).

AI_HUB_STATES = {
    "VA": "Virginia",
    "TX": "Texas",
    "OR": "Oregon",
    "IA": "Iowa",
    "NV": "Nevada",
    "GA": "Georgia",
    "OH": "Ohio",
    "IL": "Illinois",
    "AZ": "Arizona",
    "NC": "North Carolina",
}

# ─── EIA Series Queries ─────────────────────────────────────────────────────
# Each query targets a specific EIA API v2 route and produces signals
# when trend thresholds are exceeded.

# Query 1: US Monthly Electricity Generation by Source
# Route: electricity/electric-power-operational-data
# Tracks how the national generation mix is shifting (renewables vs fossil)

# Query 2: State-Level Electricity Retail Sales (Industrial Sector)
# Route: electricity/retail-sales
# Tracks power consumption in data-center-heavy states

# Query 3: US Monthly Electricity Generation — Renewables Detail
# Route: electricity/electric-power-operational-data
# Breaks out solar, wind, hydro for renewable share tracking

# ─── Trend Thresholds ───────────────────────────────────────────────────────
# Minimum change (absolute or percentage) to generate a signal.

TREND_THRESHOLDS = {
    "yoy_pct_change": 5.0,       # 5% year-over-year change triggers a signal
    "mom_pct_change": 10.0,      # 10% month-over-month change triggers a signal
    "renewable_share_milestone": [20, 25, 30, 35, 40, 45, 50],  # % milestones
}

# ─── Helper Functions ────────────────────────────────────────────────────────


def generate_signal_id(source_name: str, timestamp: str) -> str:
    """Generate unique signal ID per schema."""
    dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    date_part = dt.strftime("%Y%m%d")
    time_part = dt.strftime("%H%M%S")
    hash_part = hashlib.md5(f"{timestamp}{uuid.uuid4()}".encode()).hexdigest()[:5]
    return f"{date_part}-{source_name}-{time_part}-{hash_part}"


def get_date_range(cadence: str, days_back: int = None):
    """Return start/end dates for the query window."""
    end = datetime.now(timezone.utc)
    if days_back is not None:
        start = end - timedelta(days=days_back)
    elif cadence == "daily":
        start = end - timedelta(days=2)
    elif cadence == "weekly":
        start = end - timedelta(days=7)
    elif cadence == "monthly":
        start = end - timedelta(days=31)
    elif cadence == "quarterly":
        start = end - timedelta(days=92)
    elif cadence == "annual":
        start = end - timedelta(days=366)
    else:
        start = end - timedelta(days=7)
    return start, end


def get_date_range_prefix(start: datetime, end: datetime) -> str:
    """Get date range string for file naming."""
    return f"{start.strftime('%Y-%m-%d')}_{end.strftime('%Y-%m-%d')}"


def eia_request(route: str, params: dict, api_key: str) -> dict | None:
    """Make a request to the EIA API v2.
    Handles list-valued params by converting them to repeated key=value pairs,
    which is how the EIA API expects multi-value facets."""
    url = f"{EIA_API_BASE}/{route}/data/"
    # Build query params as a list of tuples to support repeated keys
    param_tuples = [("api_key", api_key)]
    for key, value in params.items():
        if isinstance(value, list):
            for v in value:
                param_tuples.append((key, v))
        else:
            param_tuples.append((key, value))
    try:
        resp = requests.get(url, params=param_tuples,
                            headers={"User-Agent": "espresso-ai/1.0"},
                            timeout=90)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.RequestException as e:
        print(f"    [ERROR] EIA API request failed: {e}")
        return None


# ─── Classification ─────────────────────────────────────────────────────────

SUB_VAR_KEYWORDS = {
    "ENERGY": {
        "data_center_power_intensity": [
            "data center", "industrial consumption", "retail sales",
            "commercial consumption", "electricity demand", "load growth",
        ],
        "renewable_allocation": [
            "solar", "wind", "renewable", "clean energy", "photovoltaic",
            "geothermal", "hydroelectric", "biomass",
        ],
        "grid_capacity_utilization": [
            "generation", "capacity", "utilization", "peak demand",
            "net generation", "total generation", "electricity generation",
        ],
        "renewable_capex_cost": [
            "capacity additions", "planned capacity", "new capacity",
            "nameplate capacity", "installed capacity",
        ],
        "training_energy_per_model": [
            "efficiency", "energy intensity", "consumption per",
        ],
        "water_consumption": [
            "water", "cooling", "thermal",
        ],
        "carbon_regulatory_exposure": [
            "carbon", "emissions", "co2", "greenhouse",
        ],
    },
}

# Secondary lever detection
SECONDARY_LEVER_KEYWORDS = {
    "COMPUTE": ["data center", "industrial", "server", "compute", "chip", "semiconductor"],
    "CAPITAL": ["investment", "capex", "spending", "cost", "price"],
    "GOV": ["regulation", "policy", "moratorium", "mandate", "standard"],
    "INDUSTRY": ["commercial", "enterprise", "manufacturing", "sector"],
}


def classify_signal(title: str, summary: str, signal_type: str = None) -> dict:
    """Classify an energy signal against the Scale Levers framework."""
    text = (title + " " + summary).lower()

    # Find best sub_variable within ENERGY lever
    best_sub = "grid_capacity_utilization"  # default
    best_score = 0

    for sub_var, keywords in SUB_VAR_KEYWORDS["ENERGY"].items():
        score = sum(1 for kw in keywords if kw in text)
        if score > best_score:
            best_score = score
            best_sub = sub_var

    # Override sub_variable based on signal type if provided
    if signal_type == "generation_mix":
        if best_sub not in ("renewable_allocation", "grid_capacity_utilization"):
            best_sub = "grid_capacity_utilization"
    elif signal_type == "state_consumption":
        if best_sub not in ("data_center_power_intensity", "grid_capacity_utilization"):
            best_sub = "data_center_power_intensity"
    elif signal_type == "renewable_share":
        best_sub = "renewable_allocation"
    elif signal_type == "capacity_additions":
        best_sub = "renewable_capex_cost"

    # Direction is determined by the trend analysis, not keywords
    # (caller sets direction based on whether the trend is positive or negative for scaling)

    confidence = "high" if best_score >= 3 else "medium" if best_score >= 1 else "medium"

    # Detect secondary lever
    secondary = None
    secondary_score = 0
    for lever, keywords in SECONDARY_LEVER_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text)
        if score > secondary_score and score >= 2:
            secondary_score = score
            secondary = lever

    return {
        "lever_primary": "ENERGY",
        "lever_secondary": secondary,
        "sub_variable": best_sub,
        "confidence": confidence,
    }


# ─── EIA Data Collectors ────────────────────────────────────────────────────


def collect_generation_mix(api_key: str, start: datetime, end: datetime) -> list[dict]:
    """Query US monthly electricity generation by fuel source.
    Generates signals when fuel source shares change significantly."""
    entries = []

    # We need at least 13 months of data to compute YoY trends
    query_start = start - timedelta(days=400)

    fuel_sources = [
        ("SUN", "Solar"),
        ("WND", "Wind"),
        ("NG", "Natural Gas"),
        ("NUC", "Nuclear"),
        ("COL", "Coal"),
        ("ALL", "All Sources"),
    ]

    print("  Querying US electricity generation by fuel source...")

    params = {
        "frequency": "monthly",
        "data[0]": "generation",
        "facets[fueltypeid][]": [fs[0] for fs in fuel_sources],
        "facets[location][]": "US",
        "facets[sectorid][]": "99",  # All sectors
        "start": query_start.strftime("%Y-%m"),
        "end": end.strftime("%Y-%m"),
        "sort[0][column]": "period",
        "sort[0][direction]": "desc",
        "length": "500",
    }

    data = eia_request("electricity/electric-power-operational-data", params, api_key)
    if not data or "response" not in data:
        print("    [ERROR] No generation data returned")
        return entries

    records = data["response"].get("data", [])
    print(f"    → {len(records)} data points")

    # Organize by fuel type and period
    by_fuel = {}
    for rec in records:
        fuel = rec.get("fueltypeid", "")
        period = rec.get("period", "")
        gen = rec.get("generation")
        if fuel and period and gen is not None:
            try:
                gen_val = float(gen)
            except (ValueError, TypeError):
                continue
            if fuel not in by_fuel:
                by_fuel[fuel] = {}
            by_fuel[fuel][period] = gen_val

    # Compute total generation per period for share calculations
    total_by_period = by_fuel.get("ALL", {})

    # Analyze trends for each renewable source
    for fuel_id, fuel_name in fuel_sources:
        if fuel_id == "ALL":
            continue
        fuel_data = by_fuel.get(fuel_id, {})
        if not fuel_data:
            continue

        periods = sorted(fuel_data.keys(), reverse=True)
        if len(periods) < 2:
            continue

        latest_period = periods[0]
        latest_val = fuel_data[latest_period]

        # Check if latest period is within our reporting window
        try:
            period_date = datetime.strptime(latest_period, "%Y-%m").replace(
                tzinfo=timezone.utc
            )
        except ValueError:
            continue

        # Only generate signals for data within the expanded window
        # (EIA data lags by ~2 months, so we accept recent data)
        max_lag = timedelta(days=90)
        if period_date < (start - max_lag):
            continue

        # Year-over-year comparison
        yoy_period = f"{int(latest_period[:4]) - 1}{latest_period[4:]}"
        if yoy_period in fuel_data and fuel_data[yoy_period] != 0:
            yoy_pct = ((latest_val - fuel_data[yoy_period]) / abs(fuel_data[yoy_period])) * 100

            if abs(yoy_pct) >= TREND_THRESHOLDS["yoy_pct_change"]:
                is_renewable = fuel_id in ("SUN", "WND")

                if yoy_pct > 0 and is_renewable:
                    direction = "+"
                    title = f"US {fuel_name} generation up {yoy_pct:.1f}% year-over-year ({latest_period})"
                    summary = (
                        f"{fuel_name} electricity generation rose {yoy_pct:.1f}% YoY to "
                        f"{latest_val:,.0f} thousand MWh in {latest_period}. "
                        f"Expanding renewable capacity strengthens the energy foundation for AI infrastructure scaling."
                    )
                elif yoy_pct < 0 and is_renewable:
                    direction = "-"
                    title = f"US {fuel_name} generation down {abs(yoy_pct):.1f}% year-over-year ({latest_period})"
                    summary = (
                        f"{fuel_name} generation declined {abs(yoy_pct):.1f}% YoY to "
                        f"{latest_val:,.0f} thousand MWh in {latest_period}. "
                        f"Slowing renewable growth constrains the clean energy supply available for AI data center expansion."
                    )
                elif yoy_pct > 0 and not is_renewable:
                    direction = "~"
                    title = f"US {fuel_name} generation up {yoy_pct:.1f}% year-over-year ({latest_period})"
                    summary = (
                        f"{fuel_name} generation increased {yoy_pct:.1f}% YoY to "
                        f"{latest_val:,.0f} thousand MWh in {latest_period}. "
                        f"Rising fossil generation may reflect growing total demand, including from AI workloads."
                    )
                else:
                    direction = "~"
                    title = f"US {fuel_name} generation changed {yoy_pct:+.1f}% year-over-year ({latest_period})"
                    summary = (
                        f"{fuel_name} generation shifted {yoy_pct:+.1f}% YoY to "
                        f"{latest_val:,.0f} thousand MWh in {latest_period}."
                    )

                # Compute renewable share if total available
                share_str = ""
                if total_by_period.get(latest_period) and total_by_period[latest_period] > 0:
                    share = (latest_val / total_by_period[latest_period]) * 100
                    share_str = f"{share:.1f}%"

                entries.append({
                    "signal_type": "generation_mix",
                    "title": title[:200],
                    "summary": summary[:500],
                    "direction": direction,
                    "source_url": "https://www.eia.gov/electricity/monthly/",
                    "publication_date": f"{latest_period}-01",
                    "key_facts": [
                        f"Fuel source: {fuel_name}",
                        f"Generation: {latest_val:,.0f} thousand MWh ({latest_period})",
                        f"YoY change: {yoy_pct:+.1f}%",
                        f"Share of total: {share_str}" if share_str else f"Prior period: {fuel_data.get(yoy_period, 'N/A'):,.0f} thousand MWh",
                    ],
                    "tags": [
                        f"fuel_source:{fuel_id.lower()}",
                        f"period:{latest_period}",
                        "data_type:generation_mix",
                        "geography:US",
                    ],
                    "reporting_period": latest_period,
                })

        # Month-over-month for solar/wind (more volatile)
        if fuel_id in ("SUN", "WND") and len(periods) >= 2:
            prev_period = periods[1]
            prev_val = fuel_data[prev_period]
            if prev_val and prev_val != 0:
                mom_pct = ((latest_val - prev_val) / abs(prev_val)) * 100

                if abs(mom_pct) >= TREND_THRESHOLDS["mom_pct_change"]:
                    direction = "+" if mom_pct > 0 else "-"
                    entries.append({
                        "signal_type": "generation_mix",
                        "title": f"US {fuel_name} generation {'+' if mom_pct > 0 else ''}{mom_pct:.1f}% month-over-month ({latest_period})"[:200],
                        "summary": (
                            f"{fuel_name} generation shifted {mom_pct:+.1f}% MoM. "
                            f"{'Acceleration' if mom_pct > 0 else 'Deceleration'} in renewable output "
                            f"{'expands' if mom_pct > 0 else 'narrows'} the clean energy runway for AI infrastructure."
                        )[:500],
                        "direction": direction,
                        "source_url": "https://www.eia.gov/electricity/monthly/",
                        "publication_date": f"{latest_period}-01",
                        "key_facts": [
                            f"Fuel source: {fuel_name}",
                            f"Generation: {latest_val:,.0f} thousand MWh ({latest_period})",
                            f"MoM change: {mom_pct:+.1f}%",
                            f"Prior month: {prev_val:,.0f} thousand MWh ({prev_period})",
                        ],
                        "tags": [
                            f"fuel_source:{fuel_id.lower()}",
                            f"period:{latest_period}",
                            "data_type:generation_mix",
                            "trend:month_over_month",
                            "geography:US",
                        ],
                        "reporting_period": latest_period,
                    })

    # Renewable share milestone check
    for period in sorted(total_by_period.keys(), reverse=True)[:3]:
        total = total_by_period.get(period, 0)
        if total <= 0:
            continue
        sun = by_fuel.get("SUN", {}).get(period, 0)
        wnd = by_fuel.get("WND", {}).get(period, 0)
        renewable_total = sun + wnd
        share = (renewable_total / total) * 100

        for milestone in TREND_THRESHOLDS["renewable_share_milestone"]:
            if share >= milestone and share < milestone + 5:
                entries.append({
                    "signal_type": "renewable_share",
                    "title": f"US solar+wind reaches {share:.1f}% of total electricity generation ({period})"[:200],
                    "summary": (
                        f"Combined solar and wind generation hit {share:.1f}% of US total in {period}, "
                        f"crossing the {milestone}% milestone. Rising renewable share improves the "
                        f"sustainability profile of AI data center power consumption."
                    )[:500],
                    "direction": "+",
                    "source_url": "https://www.eia.gov/electricity/monthly/",
                    "publication_date": f"{period}-01",
                    "key_facts": [
                        f"Solar+wind share: {share:.1f}%",
                        f"Solar generation: {sun:,.0f} thousand MWh",
                        f"Wind generation: {wnd:,.0f} thousand MWh",
                        f"Total generation: {total:,.0f} thousand MWh",
                    ],
                    "tags": [
                        f"milestone:{milestone}pct",
                        f"period:{period}",
                        "data_type:renewable_share",
                        "geography:US",
                    ],
                    "reporting_period": period,
                })
                break  # Only one milestone signal per period

    time.sleep(1)
    return entries


def collect_state_consumption(api_key: str, start: datetime, end: datetime) -> list[dict]:
    """Query state-level electricity retail sales for AI-hub states.
    Generates signals when industrial/commercial consumption spikes in data center states."""
    entries = []

    query_start = start - timedelta(days=400)

    print("  Querying state-level electricity retail sales (AI-hub states)...")

    state_codes = list(AI_HUB_STATES.keys())

    params = {
        "frequency": "monthly",
        "data[0]": "revenue",
        "data[1]": "sales",
        "facets[stateid][]": state_codes,
        "facets[sectorid][]": ["COM", "IND"],  # Commercial + Industrial
        "start": query_start.strftime("%Y-%m"),
        "end": end.strftime("%Y-%m"),
        "sort[0][column]": "period",
        "sort[0][direction]": "desc",
        "length": "2000",
    }

    data = eia_request("electricity/retail-sales", params, api_key)
    if not data or "response" not in data:
        print("    [ERROR] No state consumption data returned")
        return entries

    records = data["response"].get("data", [])
    print(f"    → {len(records)} data points")

    # Organize by state+sector and period
    by_state_sector = {}
    for rec in records:
        state = rec.get("stateid", "")
        sector = rec.get("sectorid", "")
        period = rec.get("period", "")
        sales = rec.get("sales")
        if state and sector and period and sales is not None:
            try:
                sales_val = float(sales)
            except (ValueError, TypeError):
                continue
            key = f"{state}_{sector}"
            if key not in by_state_sector:
                by_state_sector[key] = {}
            by_state_sector[key][period] = sales_val

    # Analyze YoY trends for each state+sector combination
    for key, period_data in by_state_sector.items():
        state_code, sector = key.split("_")
        state_name = AI_HUB_STATES.get(state_code, state_code)
        sector_name = "commercial" if sector == "COM" else "industrial"

        periods = sorted(period_data.keys(), reverse=True)
        if len(periods) < 2:
            continue

        latest_period = periods[0]
        latest_val = period_data[latest_period]

        try:
            period_date = datetime.strptime(latest_period, "%Y-%m").replace(
                tzinfo=timezone.utc
            )
        except ValueError:
            continue

        max_lag = timedelta(days=90)
        if period_date < (start - max_lag):
            continue

        # Year-over-year comparison
        yoy_period = f"{int(latest_period[:4]) - 1}{latest_period[4:]}"
        if yoy_period in period_data and period_data[yoy_period] != 0:
            yoy_pct = ((latest_val - period_data[yoy_period]) / abs(period_data[yoy_period])) * 100

            if abs(yoy_pct) >= TREND_THRESHOLDS["yoy_pct_change"]:
                # Rising consumption in data center states = potential grid strain
                if yoy_pct > 0:
                    direction = "?"  # Ambiguous: demand growth could signal both opportunity and constraint
                    summary = (
                        f"{state_name} {sector_name} electricity sales rose {yoy_pct:.1f}% YoY to "
                        f"{latest_val:,.0f} million kWh in {latest_period}. "
                        f"Rising power demand in a major data center hub signals expanding AI infrastructure "
                        f"but increases grid capacity pressure."
                    )
                else:
                    direction = "~"
                    summary = (
                        f"{state_name} {sector_name} electricity sales fell {abs(yoy_pct):.1f}% YoY to "
                        f"{latest_val:,.0f} million kWh in {latest_period}."
                    )

                entries.append({
                    "signal_type": "state_consumption",
                    "title": f"{state_name} {sector_name} electricity sales {'+' if yoy_pct > 0 else ''}{yoy_pct:.1f}% YoY ({latest_period})"[:200],
                    "summary": summary[:500],
                    "direction": direction,
                    "source_url": f"https://www.eia.gov/electricity/data/state/",
                    "publication_date": f"{latest_period}-01",
                    "key_facts": [
                        f"State: {state_name} ({state_code})",
                        f"Sector: {sector_name}",
                        f"Sales: {latest_val:,.0f} million kWh ({latest_period})",
                        f"YoY change: {yoy_pct:+.1f}%",
                    ],
                    "tags": [
                        f"state:{state_code.lower()}",
                        f"sector:{sector.lower()}",
                        f"period:{latest_period}",
                        "data_type:retail_sales",
                        f"geography:{state_name}",
                    ],
                    "reporting_period": latest_period,
                })

    time.sleep(1)
    return entries


def collect_capacity_additions(api_key: str, start: datetime, end: datetime) -> list[dict]:
    """Query planned and recent electricity capacity additions.
    Generates signals when significant new generation capacity is coming online."""
    entries = []

    query_start = start - timedelta(days=400)

    print("  Querying US electricity capacity additions...")

    params = {
        "frequency": "monthly",
        "data[0]": "nameplate-capacity-mw",
        "facets[fueltypeid][]": ["SUN", "WND", "NG", "NUC", "ALL"],
        "facets[location][]": "US",
        "start": query_start.strftime("%Y-%m"),
        "end": end.strftime("%Y-%m"),
        "sort[0][column]": "period",
        "sort[0][direction]": "desc",
        "length": "500",
    }

    data = eia_request("electricity/electric-power-operational-data", params, api_key)
    if not data or "response" not in data:
        print("    [ERROR] No capacity data returned")
        return entries

    records = data["response"].get("data", [])
    print(f"    → {len(records)} data points")

    # Organize by fuel type and period
    by_fuel = {}
    for rec in records:
        fuel = rec.get("fueltypeid", "")
        period = rec.get("period", "")
        cap = rec.get("nameplate-capacity-mw")
        if fuel and period and cap is not None:
            try:
                cap_val = float(cap)
            except (ValueError, TypeError):
                continue
            if fuel not in by_fuel:
                by_fuel[fuel] = {}
            by_fuel[fuel][period] = cap_val

    # Track capacity growth for renewables
    fuel_names = {"SUN": "Solar", "WND": "Wind", "NG": "Natural Gas", "NUC": "Nuclear"}

    for fuel_id in ["SUN", "WND"]:
        fuel_name = fuel_names.get(fuel_id, fuel_id)
        fuel_data = by_fuel.get(fuel_id, {})
        if not fuel_data:
            continue

        periods = sorted(fuel_data.keys(), reverse=True)
        if len(periods) < 2:
            continue

        latest_period = periods[0]
        latest_val = fuel_data[latest_period]

        try:
            period_date = datetime.strptime(latest_period, "%Y-%m").replace(
                tzinfo=timezone.utc
            )
        except ValueError:
            continue

        max_lag = timedelta(days=90)
        if period_date < (start - max_lag):
            continue

        # Year-over-year capacity growth
        yoy_period = f"{int(latest_period[:4]) - 1}{latest_period[4:]}"
        if yoy_period in fuel_data and fuel_data[yoy_period] != 0:
            yoy_pct = ((latest_val - fuel_data[yoy_period]) / abs(fuel_data[yoy_period])) * 100
            abs_change = latest_val - fuel_data[yoy_period]

            if abs(yoy_pct) >= TREND_THRESHOLDS["yoy_pct_change"]:
                direction = "+" if yoy_pct > 0 else "-"
                entries.append({
                    "signal_type": "capacity_additions",
                    "title": f"US {fuel_name} nameplate capacity {'+' if yoy_pct > 0 else ''}{yoy_pct:.1f}% YoY ({latest_period})"[:200],
                    "summary": (
                        f"US {fuel_name} nameplate capacity {'grew' if yoy_pct > 0 else 'declined'} "
                        f"{abs(yoy_pct):.1f}% YoY to {latest_val:,.0f} MW in {latest_period} "
                        f"({'+' if abs_change > 0 else ''}{abs_change:,.0f} MW). "
                        f"{'Accelerating' if yoy_pct > 0 else 'Slowing'} renewable capacity additions "
                        f"{'strengthen' if yoy_pct > 0 else 'weaken'} the power foundation for AI scaling."
                    )[:500],
                    "direction": direction,
                    "source_url": "https://www.eia.gov/electricity/monthly/",
                    "publication_date": f"{latest_period}-01",
                    "key_facts": [
                        f"Fuel: {fuel_name}",
                        f"Capacity: {latest_val:,.0f} MW ({latest_period})",
                        f"YoY change: {yoy_pct:+.1f}% ({abs_change:+,.0f} MW)",
                        f"Prior year: {fuel_data[yoy_period]:,.0f} MW ({yoy_period})",
                    ],
                    "tags": [
                        f"fuel_source:{fuel_id.lower()}",
                        f"period:{latest_period}",
                        "data_type:capacity",
                        "geography:US",
                    ],
                    "reporting_period": latest_period,
                })

    time.sleep(1)
    return entries


# ─── Signal Record Builder ──────────────────────────────────────────────────


def entry_to_signal_record(entry: dict, cadence: str,
                            pipeline_run_id: str, batch_id: str) -> dict:
    """Convert a collected EIA entry into an espresso·ai signal record."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    title = entry.get("title", "Untitled")
    summary = entry.get("summary", "")
    signal_type = entry.get("signal_type", "")

    # Classify
    classification = classify_signal(title, summary, signal_type)

    # Tags
    tags = list(entry.get("tags", []))
    tags.append("source_api:eia_v2")

    return {
        "signal_id": generate_signal_id(SOURCE_NAME, now),
        "source_name": SOURCE_NAME,
        "source_url": entry.get("source_url", "https://www.eia.gov/"),
        "fetch_timestamp": now,
        "agent_id": AGENT_ID,
        "cadence": cadence,
        "pipeline_run_id": pipeline_run_id,
        "collection_batch_id": batch_id,

        "lever_primary": classification["lever_primary"],
        "lever_secondary": classification["lever_secondary"],
        "direction": entry.get("direction", "~"),
        "sub_variable": classification["sub_variable"],
        "confidence": classification["confidence"],

        "title": title[:200],
        "summary": summary[:500],
        "key_facts": entry.get("key_facts", [])[:5],
        "raw_content": None,

        "publication_date": entry.get("publication_date", ""),
        "reporting_period": entry.get("reporting_period"),

        # Synthesis fields
        "signal_strength": None,
        "cross_lever_interactions": [],
        "novelty_flag": None,
        "countervailing_signals": [],
        "synthesis_notes": None,
        "is_duplicate": False,
        "duplicate_of": None,

        "in_scope": True,
        "data_quality_flags": [],
        "tags": tags,
        "schema_version": SCHEMA_VERSION,
    }


# ─── Deduplication ──────────────────────────────────────────────────────────


def deduplicate_entries(entries: list[dict]) -> tuple[list[dict], int]:
    """Remove duplicate entries by title similarity."""
    seen_titles = set()
    unique = []

    for entry in entries:
        title_key = entry.get("title", "").lower().strip()
        if title_key and title_key in seen_titles:
            continue
        if title_key:
            seen_titles.add(title_key)
        unique.append(entry)

    return unique, len(entries) - len(unique)


# ─── Validation ─────────────────────────────────────────────────────────────


def validate_and_flag(record: dict, date_start: datetime, date_end: datetime) -> dict:
    """Add quality flags based on data checks."""
    flags = list(record.get("data_quality_flags", []))

    url = record.get("source_url", "")
    if not url:
        flags.append("missing_url")

    pub_date = record.get("publication_date", "")
    if pub_date:
        try:
            pd = datetime.strptime(pub_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            # EIA data has a ~2 month lag, so we use a generous buffer
            buffer = timedelta(days=120)
            if pd < (date_start - buffer):
                flags.append("out_of_date_range")
        except ValueError:
            flags.append("invalid_date_format")

    record["data_quality_flags"] = flags
    return record


# ─── Main Pipeline ──────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="espresso·ai EIA Energy Signal Collector"
    )
    parser.add_argument("--cadence", default="weekly",
                        choices=["daily", "weekly", "monthly", "quarterly", "annual"])
    parser.add_argument("--days-back", type=int, default=None,
                        help="Override: look back N days (default: auto from cadence)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print results without writing to disk")
    args = parser.parse_args()

    # Check API key
    api_key = os.getenv("EIA_API_KEY")
    if not api_key:
        print("[ERROR] EIA_API_KEY not set. Register for a free key at:")
        print("  https://www.eia.gov/opendata/register.php")
        print("Then add to .env/.env:  EIA_API_KEY=your_key_here")
        return

    cadence = args.cadence
    now = datetime.now(timezone.utc)
    pipeline_run_id = f"{now.strftime('%Y-%m-%d')}_{cadence}_{uuid.uuid4().hex[:8]}"
    batch_id = f"batch_{now.strftime('%Y%m%d_%H%M')}"
    start_date, end_date = get_date_range(cadence, args.days_back)

    print("=" * 70)
    print("espresso·ai — EIA Energy Signal Collector")
    print("=" * 70)
    print(f"Pipeline run:      {pipeline_run_id}")
    print(f"Batch:             {batch_id}")
    print(f"Cadence:           {cadence}")
    print(f"Date range:        {start_date.strftime('%Y-%m-%d')} → {end_date.strftime('%Y-%m-%d')}")
    print(f"Source:            US Energy Information Administration (EIA API v2)")
    print("=" * 70)

    # ── Collect from EIA ──
    all_entries = []

    print(f"\n{'─' * 40}")
    print("1. US Electricity Generation by Fuel Source")
    print(f"{'─' * 40}")
    gen_entries = collect_generation_mix(api_key, start_date, end_date)
    all_entries.extend(gen_entries)
    print(f"  Signals generated: {len(gen_entries)}")

    print(f"\n{'─' * 40}")
    print("2. State-Level Electricity Consumption (AI-Hub States)")
    print(f"{'─' * 40}")
    state_entries = collect_state_consumption(api_key, start_date, end_date)
    all_entries.extend(state_entries)
    print(f"  Signals generated: {len(state_entries)}")

    print(f"\n{'─' * 40}")
    print("3. Renewable Capacity Additions")
    print(f"{'─' * 40}")
    cap_entries = collect_capacity_additions(api_key, start_date, end_date)
    all_entries.extend(cap_entries)
    print(f"  Signals generated: {len(cap_entries)}")

    # Deduplicate
    pre_dedup = len(all_entries)
    all_entries, dupes_removed = deduplicate_entries(all_entries)

    print(f"\n{'=' * 70}")
    print(f"Total collected:    {pre_dedup}")
    print(f"Duplicates removed: {dupes_removed}")
    print(f"Unique signals:     {len(all_entries)}")

    if not all_entries:
        print("\nNo energy signals generated in the target period.")
        print("This may be normal — EIA data lags by ~2 months.")
        print("Suggestions:")
        print("  - Try --cadence monthly or quarterly for more data")
        print("  - Increase --days-back to capture older data points")
        return

    # Convert to signal records
    signal_records = []
    for entry in all_entries:
        record = entry_to_signal_record(entry, cadence, pipeline_run_id, batch_id)
        record = validate_and_flag(record, start_date, end_date)
        signal_records.append(record)

    # Metrics
    type_counts = {}
    direction_counts = {}
    sub_var_counts = {}

    for entry in all_entries:
        st = entry.get("signal_type", "unknown")
        type_counts[st] = type_counts.get(st, 0) + 1

    for rec in signal_records:
        d = rec["direction"]
        direction_counts[d] = direction_counts.get(d, 0) + 1
        sv = rec["sub_variable"]
        sub_var_counts[sv] = sub_var_counts.get(sv, 0) + 1

    def count_flag(flag_name):
        return sum(1 for s in signal_records if flag_name in s.get("data_quality_flags", []))

    print(f"\nSignal Type Distribution:")
    for st, count in sorted(type_counts.items(), key=lambda x: -x[1]):
        print(f"  {st:25s}  {count:3d}")

    print(f"\nSub-Variable Distribution:")
    for sv, count in sorted(sub_var_counts.items(), key=lambda x: -x[1]):
        print(f"  {sv:35s}  {count:3d}")

    print(f"\nDirection: + {direction_counts.get('+', 0)} | - {direction_counts.get('-', 0)} | ~ {direction_counts.get('~', 0)} | ? {direction_counts.get('?', 0)}")
    print(f"Out-of-date:         {count_flag('out_of_date_range')}")

    # Write JSONL
    base_dir = Path(__file__).resolve().parent.parent.parent / "research_db" / "raw"
    base_dir.mkdir(parents=True, exist_ok=True)

    date_prefix = get_date_range_prefix(start_date, end_date)
    output_file = base_dir / f"{date_prefix}_eia_{cadence}_signals.jsonl"

    if args.dry_run:
        print(f"\n[DRY RUN] Would write {len(signal_records)} records to {output_file}")
        for rec in signal_records[:5]:
            print(f"\n  Title: {rec['title'][:80]}")
            print(f"  Lever: {rec['lever_primary']} | Direction: {rec['direction']} | Sub: {rec['sub_variable']}")
            print(f"  URL:   {rec['source_url'][:80]}")
    else:
        with open(output_file, "a", encoding="utf-8") as f:
            for record in signal_records:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        print(f"\n✓ Wrote {len(signal_records)} signal records to:")
        print(f"  {output_file}")

    # Write pipeline log
    log = {
        "pipeline_run_id": pipeline_run_id,
        "collection_batch_id": batch_id,
        "cadence": cadence,
        "source": "eia",
        "started_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "completed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "date_range": {
            "start": start_date.strftime("%Y-%m-%d"),
            "end": end_date.strftime("%Y-%m-%d"),
        },
        "total_results_raw": pre_dedup,
        "duplicates_removed": dupes_removed,
        "records_written": len(signal_records),
        "signal_type_distribution": type_counts,
        "sub_variable_distribution": sub_var_counts,
        "direction_distribution": direction_counts,
        "lever_distribution": {"ENERGY": len(signal_records)},
        "output_file": str(output_file),
        "quality_metrics": {
            "out_of_date_count": count_flag("out_of_date_range"),
        },
    }

    log_file = base_dir / f"{date_prefix}_eia_pipeline_log.json"
    if not args.dry_run:
        with open(log_file, "w", encoding="utf-8") as f:
            json.dump(log, f, indent=2, ensure_ascii=False)
        print(f"✓ Pipeline log: {log_file}")

    # Print signal sample
    print(f"\n{'=' * 70}")
    print("SAMPLE SIGNALS:")
    print(f"{'=' * 70}")
    for i, rec in enumerate(signal_records[:10], 1):
        d = rec["direction"]
        sub = rec["sub_variable"]
        title = rec["title"][:65]
        print(f"  {i:2d}. [ENERGY {d}] {sub:30s} | {title}")

    if len(signal_records) > 10:
        print(f"  ... and {len(signal_records) - 10} more")

    print(f"\n{'=' * 70}")
    print("Done. (EIA API — $0.00, free API key)")


if __name__ == "__main__":
    main()
