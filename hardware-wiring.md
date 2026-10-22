# Hardware Wiring Guide

This document describes the physical wiring and instrumentation setup for
an industrial water metering deployment. It covers meter selection, signal
conditioning, communication protocols, and integration with the data logger
that feeds the validation pipeline in this repository.

The guide is written for a textile factory context but applies to most
industrial facilities. Always consult your plant electrical engineer and
follow local codes (NEC, IEC, etc.) for the actual installation.

---

## 1. Meter selection by application

| Application | Recommended meter | Why | Wiring |
|---|---|---|---|
| Dyeing line (clean water, dye liquor) | Electromagnetic flow meter (mag meter) | No moving parts, handles dyeing chemicals and temperatures up to 90°C | 4-wire: power + pulse output |
| Washing machine feed | Electromagnetic or ultrasonic | Mag meter for accuracy, ultrasonic for non-invasive retrofit | 4-wire or 2-wire (loop-powered) |
| Boiler feed water | Turbine or coriolis | Coriolis gives mass flow if density varies; turbine for cost | 4-wire |
| Cooling tower make-up | Ultrasonic clamp-on | Non-invasive, easy retrofit on existing PVC or steel pipe | 4-wire |
| Process water main | Electromagnetic | High flow range, low pressure drop | 4-wire |
| Domestic supply | Mechanical turbine or ultrasonic | Low cost, sufficient accuracy for billing-grade tracking | 2-wire pulse |

For each meter, record the following in `templates/water-meter-register.csv`:

- `manufacturer`, `model`, `serial_number` (for traceability).
- `install_date` (for calibration-cycle calculations).
- `rollover_limit` (so the validation pipeline can detect rollover).
- `calibration_due` (the next calibration date).

---

## 2. Signal types

Industrial water meters emit one or more of these signals:

### Pulse output (dry contact or solid-state)

Each pulse represents a fixed volume (e.g., 1 pulse = 1 litre or 1 pulse =
10 litres). The data logger counts pulses and multiplies by the pulse
weight to get volume.

- **Dry contact (reed switch)** — Most common. The logger applies a
  small voltage and detects contact closures. Pull-up resistor required.
- **Solid-state (NPN/PNP open collector)** — Faster, longer life than
  reed. Requires logger input compatible with the output type.
- **Frequency output (0–10 kHz)** — Used by turbine and coriolis meters.
  Logger counts frequency in a sample window and converts to flow rate.

### Analog output (4–20 mA current loop)

The meter represents flow rate as a current in the 4–20 mA range:
- 4 mA = 0 flow
- 20 mA = full-scale flow (e.g., 100 m³/h)

The logger reads the current with an analog input and converts to flow
rate using the meter's calibration factor.

**Why 4–20 mA**: Current loops are immune to voltage drop over long cable
runs (up to ~1 km with proper wire gauge). The "live zero" of 4 mA means
a broken wire shows 0 mA, immediately distinguishable from a zero flow
reading of 4 mA.

### Digital communication (MODBUS RTU, HART, PROFIBUS, IO-Link)

Modern meters offer serial or fieldbus communication that exposes
multiple variables (total, flow rate, temperature, alarm flags) over a
single pair.

- **MODBUS RTU** (RS-485) is the de facto standard for industrial water
  meters. Half-duplex, multidrop, up to 32 devices per bus at 9600–115200
  baud.
- **HART** superimposes a digital signal on top of a 4–20 mA loop. Lets
  you read both the analog flow rate and digital diagnostics.
- **PROFIBUS-PA / IO-Link** — Used in process plants with a Siemens or
  Rockwell control system.

---

## 3. Recommended architecture — single-plant, multi-meter

For a textile factory with 6–20 water meters:

```
┌─────────────────────────────────────────────────────────────┐
│ Field meters (6–20 devices)                                 │
│ Each: pulse output OR 4-20 mA OR RS-485 MODBUS RTU           │
└──────────────────────────┬──────────────────────────────────┘
                           │
            Cable runs to plant electrical room
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ Data logger / gateway                                        │
│  ─── Digital inputs (pulse / dry contact) × 8                │
│  ─── Analog inputs (4–20 mA) × 8                             │
│  ─── RS-485 serial port × 2 (multidrop MODBUS RTU)            │
│  ─── Ethernet / Wi-Fi uplink                                 │
│  ─── Local SD card buffer                                    │
│ Recommended: Moxa ioLogik E2242 / Advantech EKI-1228 /        │
│              Wago PFC200 or similar industrial gateway       │
└──────────────────────────┬──────────────────────────────────┘
                           │
            Polling interval: 1 minute (configurable)
            Push frequency: hourly CSV upload via SFTP/HTTP
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ Ingest server (this repository's host)                       │
│  ─── Receives CSV drops into data/ folder                     │
│  ─── Runs scripts/data_validation.py on each new file        │
│  ─── Refreshes dashboard/water-dashboard.xlsx                │
│  ─── Updates dashboard/python_dashboard.png/.html             │
└─────────────────────────────────────────────────────────────┘
```

---

## 4. Wiring detail — pulse output meter

For each dry-contact pulse meter:

```
Data logger +24 V DC ────────┬─────────────┐
                             │             │
                            [R_pullup]    [Meter reed]
                           10 kΩ 1/4 W    (closes on each pulse)
                             │             │
Data logger DI+ ─────────────┴─────────────┘
Data logger DI- ──────────────────────────── (signal common / GND)
Data logger GND ────────────────────────────
```

Cable: shielded twisted pair, 20–22 AWG. Shield grounded at the logger
end only. Maximum cable length: ~100 m at 24 V; reduce to 50 m at 12 V.

Configuration on the logger:
- Pulse weight = meter's K-factor (e.g., 1 pulse = 1 litre for a typical
  domestic meter; 1 pulse = 100 litres for a large mag meter).
- Debounce time = 50 ms (prevents double-counting from reed contact bounce).
- Polling interval = totalize over 1 minute; report cumulative count.

---

## 5. Wiring detail — 4–20 mA analog meter

```
Data logger AI+ (24 V loop supply) ──────┐
                                        │
                              ┌─────────┴─────────┐
                              │  Meter transmitter │
                              │  2-wire loop-powered│
                              └─────────┬─────────┘
                                        │
Data logger AI- (current return) ────────┘
```

Cable: shielded twisted pair, 20–22 AWG. Maximum loop resistance per the
logger's spec (typically 250–600 Ω including cable and the meter's internal
resistor).

Configuration on the logger:
- Input range: 4–20 mA.
- Scaling: 4 mA = 0 m³/h, 20 mA = full-scale per the meter's datasheet.
- Conversion: cumulative volume = Σ (flow_rate × sample_interval).

For meters with **3-wire or 4-wire** transmitters (externally powered,
not loop-powered), provide a separate 24 V DC supply to the meter and wire
the analog output to the logger AI+ / AI- terminals.

---

## 6. Wiring detail — MODBUS RTU (RS-485) multidrop

For up to 32 MODBUS meters on a single bus:

```
Data logger RS-485 (+) ───┬──────┬──────┬────── (up to 32 devices)
                          │      │      │
                       Meter1  Meter2  Meter3   ...
                          │      │      │
Data logger RS-485 (−) ───┴──────┴──────┴──────

Terminating resistors (120 Ω) at both ends of the bus.
```

Cable: 1 twisted pair plus drain wire, 22 AWG, shielded. Belden 9842 or
equivalent. Maximum total bus length: ~1.2 km at 9600 baud; ~400 m at
115200 baud.

Configuration:
- Baud rate: 9600 (default for most meters).
- Data bits: 8, parity: None, stop bits: 1 (8N1).
- Each meter needs a unique MODBUS slave address (1–247).
- The logger polls each meter's input register holding the cumulative
  totalizer (e.g., register 4001 for many mag meters).

Common MODBUS function codes used:
- Function 03 (Read Holding Registers) — read totalizer, flow rate.
- Function 04 (Read Input Registers) — read-only telemetry values.

---

## 7. Power supply

- Each meter: 24 V DC ±10% from a dedicated power supply rated for
  instrumentation (linear or switched mode with low ripple, < 50 mV p-p).
- Each data logger: 24 V DC, 30 W minimum. Use a UPS-backed supply so
  readings continue during a power outage.
- Cable runs: keep instrument power cables at least 30 cm from
  high-current motor cables to avoid induced noise.

---

## 8. Grounding and shielding

- **Single-point ground** the cable shields at the data logger end only.
  Grounding both ends creates ground loops that inject noise.
- **Use isolated RS-485 repeaters** if meters are in different plant
  buildings with different ground potentials.
- **Bond all field enclosures** to the plant ground grid with 6 AWG
  minimum conductors.
- **Install surge protection** on any cable entering from outside the
  building (e.g., outdoor cooling tower meters). Gas-discharge tubes or
  MOVs rated for the signal type.

---

## 9. Commissioning checklist

Before commissioning each meter, verify:

- [ ] Pipe is full of water at zero flow (mag meters read zero only when
  the pipe is full; an empty pipe reads as no flow even if the pipe is
  actually in service).
- [ ] Meter is installed with the required straight-pipe lengths upstream
  (typically 5 × pipe diameter) and downstream (typically 3 × pipe
  diameter). Mag meters in particular are sensitive to flow profile
  distortion.
- [ ] Arrow on the meter body points in the flow direction.
- [ ] Wiring matches the meter's terminal labels (polarity matters for
  analog and MODBUS).
- [ ] Calibration certificate is on file and `calibration_due` in the
  register is set correctly.
- [ ] The data logger sees the meter: a single poll returns a valid
  totalizer value, not an error code.
- [ ] The pulse weight (or analog scaling, or MODBUS register scaling)
  is set correctly in the logger — verify by manual draw test (fill a
  known volume container and confirm the logger's count matches).
- [ ] After 24 hours of operation, compare the logger's reported
  consumption against a manual meter reading taken at the start and
  end of the period. Tolerance: ±2% for electromagnetic, ±5% for
  ultrasonic, ±1% for coriolis.

Record the commissioning date and verifier's initials in the meter
register's `notes` column.

---

## 10. Maintenance schedule

| Frequency | Task |
|---|---|
| Weekly | Visual inspection of field enclosures; check for water ingress, corroded terminals |
| Monthly | Compare logger-reported consumption against manual meter reading; investigate any deviation >5% |
| Quarterly | Verify data logger clock (NTP sync); review anomaly log |
| Annually | Recalibrate meters per manufacturer's spec; update `calibration_due` |
| Every 5 years | Replace reed-switch pulse meters (contacts wear); replace desiccant in field enclosures |

---

## 11. Safety

- **Lockout-tagout** before wiring or unwiring any meter. Even at 24 V DC,
  unexpected start of the production line can cause fluid surges that
  damage the meter or injure personnel.
- **PPE**: insulated gloves and safety glasses when working in plant
  electrical panels.
- **Hot work**: any welding near a flow meter installation must be done
  with the meter disconnected — the meter's electronics are not rated
  for the high-frequency currents induced by nearby welding.
- **Confined space**: cooling-tower and boiler installations often
  require confined-space entry. Follow your plant's confined-space
  permit procedure.

---

## 12. What this repository does NOT cover

- **Hazardous-area installations** (Zone 1 / Zone 2 / Class I Div 2)
  require intrinsically-safe barriers and explosion-proof enclosures
  not described here. Engage a certified electrical contractor.
- **Smart meter protocols** beyond MODBUS RTU (BACnet, LoRaWAN, NB-IoT)
  are out of scope; the principles are similar but the hardware differs.
- **Sub-metering** for tenant billing in multi-occupier buildings is
  subject to legal metrology requirements in most jurisdictions. Use
  MID-certified meters and consult your local weights and measures
  authority.
- **Hydraulic modeling** of the plant water network (pipe sizing,
  pressure drop, valve selection) is a separate engineering discipline
  not addressed by this repository.

For any of the above, treat this guide as background context only and
engage a qualified specialist.
