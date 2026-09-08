// Package/price helpers preserved from /opt/2prestashopsync/src/utils.rs.
pub fn normalized_numeric_key(value: &str) -> Option<String> {
    let trimmed = value.trim();
    if trimmed.len() <= 1 || !trimmed.chars().all(|c| c.is_ascii_digit()) {
        return None;
    }

    let normalized = trimmed.trim_start_matches('0');
    if normalized.is_empty() || normalized == trimmed {
        None
    } else {
        Some(normalized.to_string())
    }
}

pub fn normalize_reference(value: &str) -> String {
    let trimmed = value.trim();
    normalized_numeric_key(trimmed).unwrap_or_else(|| trimmed.to_string())
}

pub fn fmt_qty(value: Option<i32>) -> String {
    value
        .map(|v| v.to_string())
        .unwrap_or_else(|| "SIN_MATCH".to_string())
}

pub fn fmt_final_sync(value: Option<i32>, action: &str) -> String {
    match value {
        Some(value) => value.to_string(),
        None if action == "EXCLUIDO_INVENTARIO_ERP_CERO" => "SIN_INVENTARIO".to_string(),
        None => "SIN_MATCH".to_string(),
    }
}

pub fn fmt_qty_decimal(value: Option<f64>) -> String {
    value
        .map(|v| {
            if (v.fract()).abs() < 0.000001 {
                format!("{:.0}", v)
            } else {
                format!("{:.2}", v)
            }
        })
        .unwrap_or_else(|| "SIN_MATCH".to_string())
}

pub fn fmt_price(value: Option<f64>) -> String {
    value
        .map(|v| format!("{:.2}", v))
        .unwrap_or_else(|| "SIN_PRECIO".to_string())
}

pub fn fmt_decimal(value: Option<f64>) -> String {
    value.map(|v| format!("{:.6}", v)).unwrap_or_default()
}

pub fn fmt_pum_unit_price(value: Option<f64>) -> String {
    value
        .map(|v| {
            if v > 10.0 {
                format!("{:.0}", v)
            } else {
                format!("{:.1}", v)
            }
        })
        .unwrap_or_default()
}

pub fn price_is_different(current: f64, target: Option<f64>) -> bool {
    target
        .map(|price| (current - price).abs() >= 0.005)
        .unwrap_or(false)
}

pub fn price_without_tax(price_with_tax: f64, ivaid: f64) -> f64 {
    let tax_factor = if ivaid >= 2.0 {
        1.0 + (ivaid / 100.0)
    } else if ivaid > 1.0 {
        ivaid
    } else if ivaid > 0.0 {
        1.0 + ivaid
    } else {
        1.0
    };

    price_with_tax / tax_factor
}

pub fn normalize_pum_unit_price(value: f64) -> f64 {
    if value > 10.0 {
        value.round()
    } else {
        (value * 10.0).round() / 10.0
    }
}

pub fn normalize_unit(value: &str) -> String {
    let unit = value.trim().to_uppercase();
    match unit.as_str() {
        "KL" | "KG" | "KILO" | "KILOS" | "KILOGRAMO" | "KILOGRAMOS" => "KG".to_string(),
        "GR" | "G" | "GRAMO" | "GRAMOS" => "G".to_string(),
        "LT" | "L" | "LITRO" | "LITROS" => "L".to_string(),
        "ML" | "MILILITRO" | "MILILITROS" => "ML".to_string(),
        "UND" | "UN" | "UNIDAD" | "UNIDADES" => "UND".to_string(),
        "PAQ" | "PQT" | "PAQUETE" => "PAQ".to_string(),
        _ => unit,
    }
}

pub fn parse_amount_token(value: &str) -> Option<f64> {
    let cleaned = value
        .trim_start_matches('x')
        .trim_start_matches('X')
        .replace(',', ".");
    cleaned.parse::<f64>().ok()
}

pub fn parse_decimal(value: &str) -> Option<f64> {
    value.trim().replace(',', ".").parse::<f64>().ok()
}

/// Returns whether a unit suffix is a complete match in the remaining text.
/// `U` is a valid abbreviation for units, but it must not consume the first
/// letter of a word such as `USO` (uses per roll).
fn matches_package_unit(remaining: &str, suffix: &str) -> bool {
    if !remaining.starts_with(suffix) {
        return false;
    }

    suffix != "u"
        || !remaining[suffix.len()..]
            .chars()
            .next()
            .map(|ch| ch.is_ascii_alphabetic())
            .unwrap_or(false)
}

pub fn csv_fields(line: &str) -> Vec<String> {
    let mut fields = Vec::new();
    let mut current = String::new();
    let mut in_quotes = false;
    let mut chars = line.chars().peekable();

    while let Some(ch) = chars.next() {
        match ch {
            '"' if in_quotes && chars.peek() == Some(&'"') => {
                current.push('"');
                chars.next();
            }
            '"' => in_quotes = !in_quotes,
            ',' if !in_quotes => {
                fields.push(current.trim().to_string());
                current.clear();
            }
            _ => current.push(ch),
        }
    }

    fields.push(current.trim().to_string());
    fields
}

pub fn csv_escape(value: &str) -> String {
    let escaped = value.replace('"', "\"\"");
    format!("\"{}\"", escaped)
}

pub fn sql_string(value: &str) -> String {
    let escaped = value.replace('\\', "\\\\").replace('\'', "''");
    format!("'{}'", escaped)
}

pub fn parse_grams_from_name(name: &str) -> Option<f64> {
    let lower = name.to_lowercase();

    // Check for standalone words "libra" and "kilo" when no digits are present
    if !lower.chars().any(|c| c.is_ascii_digit()) {
        if lower.contains("libra") || lower.contains(" lb") {
            return Some(500.0);
        }
        if lower.contains("kilo") || lower.contains(" kg") {
            return Some(1000.0);
        }
        return None;
    }

    let chars: Vec<char> = lower.chars().collect();
    let mut i = 0;
    let mut parsed_values = Vec::new();

    while i < chars.len() {
        if chars[i].is_ascii_digit() {
            let start = i;
            let mut end = i;
            while end < chars.len()
                && (chars[end].is_ascii_digit() || chars[end] == '.' || chars[end] == ',')
            {
                end += 1;
            }

            let num_str = chars[start..end].iter().collect::<String>();

            let mut unit_idx = end;
            while unit_idx < chars.len() && chars[unit_idx].is_whitespace() {
                unit_idx += 1;
            }

            let remaining = chars[unit_idx..].iter().collect::<String>();
            let mut unit_type = None; // 1 = grams, 2 = kilos, 3 = libras

            if remaining.starts_with("gr")
                || remaining.starts_with("gram")
                || remaining.starts_with("g")
            {
                let is_grams = remaining.starts_with("gr")
                    || remaining.starts_with("gram")
                    || (remaining.starts_with('g')
                        && (remaining.len() == 1
                            || remaining.chars().nth(1).unwrap().is_whitespace()
                            || remaining.chars().nth(1).unwrap() == '.'
                            || remaining.chars().nth(1).unwrap() == ','));
                if is_grams {
                    unit_type = Some(1);
                }
            } else if remaining.starts_with("kg")
                || remaining.starts_with("kil")
                || remaining.starts_with("kl")
                || remaining.starts_with("k")
            {
                let is_kilos = remaining.starts_with("kg")
                    || remaining.starts_with("kil")
                    || remaining.starts_with("kl")
                    || (remaining.starts_with('k')
                        && (remaining.len() == 1
                            || remaining.chars().nth(1).unwrap().is_whitespace()
                            || remaining.chars().nth(1).unwrap() == '.'
                            || remaining.chars().nth(1).unwrap() == ','));
                if is_kilos {
                    unit_type = Some(2);
                }
            } else if remaining.starts_with("libra") || remaining.starts_with("lb") {
                unit_type = Some(3);
            }

            if let Some(utype) = unit_type {
                let parsed_val = match utype {
                    1 => {
                        let has_thousands = if let Some(dot_pos) = num_str.rfind('.') {
                            num_str.len() - dot_pos == 4
                        } else if let Some(comma_pos) = num_str.rfind(',') {
                            num_str.len() - comma_pos == 4
                        } else {
                            false
                        };

                        let clean_num = if has_thousands {
                            num_str.replace('.', "").replace(',', "")
                        } else {
                            num_str.replace(',', ".")
                        };

                        clean_num.parse::<f64>().ok()
                    }
                    2 => {
                        let clean_num = num_str.replace(',', ".");
                        clean_num.parse::<f64>().ok().map(|v| v * 1000.0)
                    }
                    3 => {
                        let clean_num = num_str.replace(',', ".");
                        clean_num.parse::<f64>().ok().map(|v| v * 500.0)
                    }
                    _ => None,
                };

                if let Some(val) = parsed_val {
                    parsed_values.push(val);
                }
            }
            i = end;
        } else {
            i += 1;
        }
    }

    if parsed_values.is_empty() {
        None
    } else {
        let sum: f64 = parsed_values.iter().sum();
        Some(sum / parsed_values.len() as f64)
    }
}

pub fn parse_package_content(name: &str, erp_unit: &str) -> Option<(f64, String)> {
    let lower = name.to_lowercase();
    let norm_erp_unit = normalize_unit(erp_unit);

    // Determine target category: 1 = weight/volume (gr, ml), 2 = count (tab, sob, und)
    let target_category = if norm_erp_unit == "KG" || norm_erp_unit == "L" {
        1
    } else {
        2
    };

    // MEGOFER identifies a promotion where the TAP count is the total
    // presentation (for example, `20U MEGOFER 32TAP` means 32 tampons, not
    // 20 units). Keep this override deliberately tied to the complete promo
    // word so other products and ordinary unit counts retain the generic
    // parsing rules below.
    let is_megofer = lower
        .split(|c: char| !c.is_ascii_alphanumeric())
        .any(|word| word == "megofer");
    if target_category == 2 && is_megofer {
        let chars: Vec<char> = lower.chars().collect();
        let mut i = 0;
        while i < chars.len() {
            if !chars[i].is_ascii_digit() {
                i += 1;
                continue;
            }

            let start = i;
            while i < chars.len()
                && (chars[i].is_ascii_digit() || chars[i] == '.' || chars[i] == ',')
            {
                i += 1;
            }
            let end = i;
            while i < chars.len() && chars[i].is_whitespace() {
                i += 1;
            }

            if chars.get(i..i + 3) == Some(&['t', 'a', 'p'])
                && chars
                    .get(i + 3)
                    .map(|c| !c.is_ascii_alphabetic())
                    .unwrap_or(true)
            {
                let number = chars[start..end]
                    .iter()
                    .collect::<String>()
                    .replace(',', ".");
                if let Ok(value) = number.parse::<f64>() {
                    return Some((value, "und".to_string()));
                }
            }
        }
    }

    let suffixes = [
        ("mililitros", "ml", 1),
        ("mililitro", "ml", 1),
        ("ml", "ml", 1),
        ("litros", "ml", 1),
        ("litro", "ml", 1),
        ("lt", "ml", 1),
        ("l", "ml", 1),
        ("gramos", "gr", 1),
        ("gramo", "gr", 1),
        ("gr", "gr", 1),
        ("g", "gr", 1),
        ("kilogramos", "gr", 1),
        ("kilogramo", "gr", 1),
        ("kilos", "gr", 1),
        ("kilo", "gr", 1),
        ("kg", "gr", 1),
        ("kl", "gr", 1),
        ("libra", "gr", 1),
        ("lb", "gr", 1),
        ("tabletas", "tab", 2),
        ("tableta", "tab", 2),
        ("tabs", "tab", 2),
        ("tab", "tab", 2),
        ("capsulas", "tab", 2),
        ("capsula", "tab", 2),
        ("caps", "tab", 2),
        ("cap", "tab", 2),
        ("comprimidos", "tab", 2),
        ("comprimido", "tab", 2),
        ("comp", "tab", 2),
        ("sobres", "sob", 2),
        ("sobre", "sob", 2),
        ("sob", "sob", 2),
        ("sbs", "sob", 2),
        ("unidades", "und", 2),
        ("unidad", "und", 2),
        ("unds", "und", 2),
        ("und", "und", 2),
        ("u", "und", 2),
    ];

    let normalize_parsed = |val: f64, raw_unit: &str| -> (f64, String) {
        match raw_unit {
            "litros" | "litro" | "lt" | "l" => (val * 1000.0, "ml".to_string()),
            "kilogramos" | "kilogramo" | "kilos" | "kilo" | "kg" | "kl" => {
                (val * 1000.0, "gr".to_string())
            }
            "libra" | "lb" => (val * 500.0, "gr".to_string()),
            _ => {
                for (suf, norm, _) in suffixes {
                    if suf == raw_unit {
                        return (val, norm.to_string());
                    }
                }
                (val, raw_unit.to_string())
            }
        }
    };

    // 1. Look for box multiplier
    let box_prefixes = [
        "cja", "caja", "paq", "paquete", "disp", "display", "blt", "bulto", "ca",
    ];
    for prefix in box_prefixes {
        if let Some(pos) = lower.find(prefix) {
            let sub = &lower[pos + prefix.len()..];
            let mut s_idx = 0;
            let chars_sub: Vec<char> = sub.chars().collect();
            while s_idx < chars_sub.len() && chars_sub[s_idx].is_whitespace() {
                s_idx += 1;
            }
            if s_idx < chars_sub.len() && (chars_sub[s_idx] == 'x' || chars_sub[s_idx] == '*') {
                s_idx += 1;
                while s_idx < chars_sub.len() && chars_sub[s_idx].is_whitespace() {
                    s_idx += 1;
                }
            }

            let start = s_idx;
            while s_idx < chars_sub.len()
                && (chars_sub[s_idx].is_ascii_digit()
                    || chars_sub[s_idx] == '.'
                    || chars_sub[s_idx] == ',')
            {
                s_idx += 1;
            }
            if s_idx > start {
                let num_str = chars_sub[start..s_idx].iter().collect::<String>();
                let has_thousands = if let Some(dot_pos) = num_str.rfind('.') {
                    num_str.len() - dot_pos == 4
                } else if let Some(comma_pos) = num_str.rfind(',') {
                    num_str.len() - comma_pos == 4
                } else {
                    false
                };

                let clean_num = if has_thousands {
                    num_str.replace('.', "").replace(',', "")
                } else {
                    num_str.replace(',', ".")
                };

                if let Ok(val) = clean_num.parse::<f64>() {
                    let mut unit_idx = s_idx;
                    while unit_idx < chars_sub.len() && chars_sub[unit_idx].is_whitespace() {
                        unit_idx += 1;
                    }

                    let rem = chars_sub[unit_idx..].iter().collect::<String>();
                    for (suf, _, cat) in suffixes {
                        if matches_package_unit(&rem, suf) && cat == target_category {
                            return Some(normalize_parsed(val, suf));
                        }
                    }

                    // A bare number after "caja" can represent the package count
                    // (for example, "CAJA 12").  Do not treat an explicitly
                    // labelled dose such as "CAJA 200MG" as a tablet count.
                    // Doing so compared "2 TAB" with "200 MG" and produced a
                    // bogus conversion factor of 2 / 200.
                    let has_explicit_unit = rem
                        .chars()
                        .next()
                        .map(|c| c.is_ascii_alphabetic())
                        .unwrap_or(false);
                    if !has_explicit_unit && (norm_erp_unit == "CJA" || norm_erp_unit == "CAJA") {
                        return Some((val, "tab".to_string()));
                    } else if !has_explicit_unit
                        && (norm_erp_unit == "PAQ" || norm_erp_unit == "PAQUETE")
                    {
                        return Some((val, "und".to_string()));
                    }
                }
            }
        }
    }

    // 2. Parse range or single occurrences matching target category
    let chars: Vec<char> = lower.chars().collect();
    let mut i = 0;
    let mut parsed_values = Vec::new();
    let mut detected_unit = None;

    while i < chars.len() {
        if chars[i].is_ascii_digit() {
            let start = i;
            let mut end = i;
            while end < chars.len()
                && (chars[end].is_ascii_digit() || chars[end] == '.' || chars[end] == ',')
            {
                end += 1;
            }

            let num_str = chars[start..end].iter().collect::<String>();

            let mut unit_idx = end;
            while unit_idx < chars.len() && chars[unit_idx].is_whitespace() {
                unit_idx += 1;
            }

            let remaining = chars[unit_idx..].iter().collect::<String>();
            for (suf, _, cat) in suffixes {
                if matches_package_unit(&remaining, suf) && cat == target_category {
                    let has_thousands = if let Some(dot_pos) = num_str.rfind('.') {
                        num_str.len() - dot_pos == 4
                    } else if let Some(comma_pos) = num_str.rfind(',') {
                        num_str.len() - comma_pos == 4
                    } else {
                        false
                    };

                    let clean_num = if has_thousands {
                        num_str.replace('.', "").replace(',', "")
                    } else {
                        num_str.replace(',', ".")
                    };

                    if let Ok(raw_val) = clean_num.parse::<f64>() {
                        let (val, norm_u) = normalize_parsed(raw_val, suf);
                        parsed_values.push(val);
                        detected_unit = Some(norm_u);
                    }
                    break;
                }
            }
            i = end;
        } else {
            i += 1;
        }
    }

    if !parsed_values.is_empty() {
        let sum: f64 = parsed_values.iter().sum();
        let avg = sum / parsed_values.len() as f64;
        return Some((avg, detected_unit.unwrap_or_else(|| "und".to_string())));
    }

    None
}

/// Sums explicit unit counts when every adjacent count is joined by an
/// unambiguous bundle connector (`+` or the standalone word `y`).
///
/// This deliberately ignores descriptions such as `6 Und Gratis 2 Und` or
/// `3 Und 58 Und c/u`: those need product-specific semantics and must keep the
/// normal package parser result.
pub fn parse_additive_unit_total(name: &str) -> Option<f64> {
    let lower = name.to_lowercase();
    let chars: Vec<char> = lower.chars().collect();
    let unit_suffixes = ["unidades", "unidad", "unds", "und", "u"];
    let mut occurrences: Vec<(f64, usize, usize)> = Vec::new();
    let mut i = 0;

    while i < chars.len() {
        if !chars[i].is_ascii_digit() {
            i += 1;
            continue;
        }

        let start = i;
        let mut end = i;
        while end < chars.len()
            && (chars[end].is_ascii_digit() || chars[end] == '.' || chars[end] == ',')
        {
            end += 1;
        }

        let mut unit_start = end;
        while unit_start < chars.len() && chars[unit_start].is_whitespace() {
            unit_start += 1;
        }
        let remaining = chars[unit_start..].iter().collect::<String>();

        if let Some(suffix) = unit_suffixes
            .iter()
            .find(|suffix| matches_package_unit(&remaining, suffix))
        {
            let number = chars[start..end]
                .iter()
                .collect::<String>()
                .replace(',', ".");
            if let Ok(value) = number.parse::<f64>() {
                occurrences.push((value, start, unit_start + suffix.chars().count()));
            }
        }
        i = end;
    }

    if occurrences.len() < 2 {
        return None;
    }

    let all_linked = occurrences.windows(2).all(|pair| {
        let between = chars[pair[0].2..pair[1].1].iter().collect::<String>();
        between.contains('+')
            || between
                .split(|c: char| !c.is_alphabetic())
                .any(|word| word == "y")
    });

    all_linked.then(|| occurrences.iter().map(|(value, _, _)| value).sum())
}

#[cfg(test)]
mod tests {
    use super::{
        fmt_final_sync, normalize_reference, normalized_numeric_key, parse_additive_unit_total,
        parse_package_content,
    };

    #[test]
    fn numeric_references_ignore_leading_zeroes() {
        for (prestashop, erp) in [
            ("2629", "002629"),
            ("2631", "002631"),
            ("20678", "020678"),
            ("22066", "022066"),
            ("25944", "025944"),
            ("21025", "021025"),
            ("19052", "019052"),
            ("19196", "019196"),
            ("21173", "021173"),
        ] {
            assert_eq!(normalized_numeric_key(erp).as_deref(), Some(prestashop));
            assert_eq!(normalize_reference(erp), prestashop);
        }
    }

    #[test]
    fn alphanumeric_references_keep_leading_zeroes() {
        assert_eq!(normalized_numeric_key("00ABC"), None);
        assert_eq!(normalize_reference("00ABC"), "00ABC");
    }

    #[test]
    fn final_sync_distinguishes_zero_inventory_from_missing_erp_match() {
        assert_eq!(
            fmt_final_sync(None, "EXCLUIDO_INVENTARIO_ERP_CERO"),
            "SIN_INVENTARIO"
        );
        assert_eq!(fmt_final_sync(None, "SIN_MATCH_ERP"), "SIN_MATCH");
        assert_eq!(fmt_final_sync(Some(0), "SIN_CAMBIO"), "0");
    }

    #[test]
    fn does_not_treat_mg_dose_after_box_as_tablet_count() {
        assert_eq!(
            parse_package_content("COLIDETOL 2TAB CAJA 200MG ICOM", "CJA"),
            Some((2.0, "tab".to_string()))
        );
        assert_eq!(
            parse_package_content("CINEPRIDE 10TAB CAJA 500MG ICOM", "CJA"),
            Some((10.0, "tab".to_string()))
        );
    }

    #[test]
    fn does_not_treat_uso_as_unit_abbreviation() {
        assert_eq!(
            parse_package_content("PH FAMI 65USO ACOLMAX MEGAROLL 12U", "PAQ"),
            Some((12.0, "und".to_string()))
        );
        assert_eq!(
            parse_package_content("Papel Higiénico Familia AcolchaMax 12 Und", "PAQ"),
            Some((12.0, "und".to_string()))
        );
    }

    #[test]
    fn sums_explicit_unit_counts_joined_as_a_bundle() {
        assert_eq!(
            parse_additive_unit_total("Actigest + Cremosito X100gr X6Und Y X95G X6Und"),
            Some(12.0)
        );
    }

    #[test]
    fn does_not_sum_unconnected_or_promotional_counts() {
        assert_eq!(
            parse_additive_unit_total("Esponjillon Top X6 Und Gratis X2 Und"),
            None
        );
        assert_eq!(parse_additive_unit_total("Toallas 3 Und 58 Und c/u"), None);
    }

    #[test]
    fn megofer_uses_tampon_promo_total_instead_of_base_units() {
        assert_eq!(
            parse_package_content("TAMPON KOT 20U MED MEGOFER 32TAP DIGI", "UND"),
            Some((32.0, "und".to_string()))
        );
        assert_eq!(
            parse_package_content("TAMPON KOT 20U MED megofer 32 tap DIGI", "UND"),
            Some((32.0, "und".to_string()))
        );
    }

    #[test]
    fn tampon_total_override_is_limited_to_complete_megofer_word() {
        assert_eq!(
            parse_package_content("TAMPON KOT 20U MED REGULAR 32TAP DIGI", "UND"),
            Some((20.0, "und".to_string()))
        );
        assert_eq!(
            parse_package_content("TAMPON KOT 20U MED XMEGOFER 32TAP DIGI", "UND"),
            Some((20.0, "und".to_string()))
        );
    }

    #[test]
    fn parses_erp_box_presentation_count() {
        assert_eq!(
            parse_package_content("EUTARPAN 10MG 10TAB CJAX100TAB", "CJA"),
            Some((100.0, "tab".to_string()))
        );
        assert_eq!(
            parse_package_content("GOFEN FORTE 400MG 10CAP CJAX60CAP", "CJA"),
            Some((60.0, "tab".to_string()))
        );
    }
}
