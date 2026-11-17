---
version: 1
---
You read an invoice for work done in or on a home. Copy what is printed; never guess and never
add up amounts yourself. Leave a field empty when the invoice does not state it.

- labour_gross: the cost of labour, travel and machines including VAT, as printed. If only net
  labour and a VAT rate are shown, leave it empty and fill labour_net and vat_rate instead.
- labour_net, vat_rate: as printed, only when labour_gross is not shown.
- material_gross: the cost of material and parts including VAT, if shown separately.
- total: the invoice total including VAT, with its currency.
- work_date: the day the work was done or finished (Leistungsdatum, Ausführungszeitraum end).
- kind: "building" (new or replaced parts of the building: roof, windows, heating installation,
  bathroom renovation, insulation), "craftsman" (repairs, servicing, inspections, painting,
  chimney sweep), or "household" (cleaning, gardening, window cleaning, care services).
- paid_in_cash: true only if the invoice says it was paid in cash ("bar erhalten", "bar bezahlt").
- task: if the work is one of these, its id: heating_service, chimney_sweep, smoke_detectors,
  gutters, heat_pump_service, water_heater, roof_check, gas_check. Otherwise empty.

Title: {title}
Values already read: {facts}

{content}
