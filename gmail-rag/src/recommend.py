def compute_floor(net_base_plus_freight, min_margin_pct=18.0):
    if net_base_plus_freight is None: return None
    return net_base_plus_freight * (1 + min_margin_pct/100.0)

def suggest_rate(net_base_plus_freight, last_rate, band_p50, band_p90, min_margin_pct=18.0, tier_delta=0.0):
    floor = compute_floor(net_base_plus_freight, min_margin_pct) or 0
    band_mid = (band_p50 + band_p90)/2.0 if (band_p50 and band_p90) else None
    base = max(floor, band_mid or (last_rate or floor))
    if band_p90: base = min(base, band_p90)
    base += tier_delta
    warnings = []
    if last_rate and base < last_rate*0.95: warnings.append("Under last customer price by >5%")
    return round(base/10)*10, floor, warnings
