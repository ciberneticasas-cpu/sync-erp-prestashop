//! SQL Server reader. No general SQL executor, no write or production fallback.
#![allow(dead_code)]
mod legacy;
use futures_util::TryStreamExt;
use serde_json::{json, Value};
use std::{collections::HashMap, fs, io::{self, Read}};
use tiberius::{Client, Config, QueryItem};
use tokio::net::TcpStream;
use tokio_util::compat::{Compat, TokioAsyncWriteCompatExt};

async fn select(client: &mut Client<Compat<TcpStream>>, sql: &str) -> Result<Vec<Value>, Box<dyn std::error::Error>> {
    if !sql.trim_start().starts_with("SELECT ") { return Err("Solo SELECT permitido".into()); }
    let mut stream = client.query(sql, &[]).await?;
    let mut result = vec![];
    while let Some(item) = stream.try_next().await? {
        if let QueryItem::Row(row) = item {
            let mut obj = serde_json::Map::new();
            for (i, col) in row.columns().iter().enumerate() {
                obj.insert(col.name().into(), json!(row.get::<&str, _>(i).unwrap_or("").trim()));
            }
            result.push(Value::Object(obj));
        }
    }
    Ok(result)
}

fn string<'a>(v: &'a Value, k: &str) -> &'a str { v[k].as_str().unwrap_or("") }

#[tokio::main]
async fn main() {
    if let Err(_) = run().await {
        eprintln!("No se pudo leer ERP. Revise .env, conectividad 192.168.0.231 y esquema; no se muestran secretos.");
        std::process::exit(1);
    }
}

async fn run() -> Result<(), Box<dyn std::error::Error>> {
    let mut input = String::new(); io::stdin().read_to_string(&mut input)?;
    let request: Value = serde_json::from_str(&input)?;
    let path = request["env_file"].as_str().ok_or("Falta env_file")?;
    let mut env = HashMap::new();
    for line in fs::read_to_string(path)?.lines() {
        let line = line.trim();
        if line.starts_with('#') { continue; }
        if let Some((k,v)) = line.split_once('=') { env.insert(k.trim().to_uppercase(), v.trim().trim_matches('"').trim_matches('\'').to_string()); }
    }
    let get = |key: &str| env.get(key).map(String::as_str).unwrap_or("");
    let host = if get("ERP_HOST").is_empty() { get("MERCABOY_ERP_HOST") } else { get("ERP_HOST") };
    if host != "192.168.0.231" { return Err("Destino ERP bloqueado".into()); }
    let mut config = Config::new();
    config.host(host); config.port(get("MERCABOY_ERP_PORT").parse().unwrap_or(1433));
    config.database(get("MERCABOY_ERP_DATABASE"));
    config.authentication(tiberius::AuthMethod::sql_server(get("MERCABOY_ERP_USER"), get("MERCABOY_ERP_PASSWORD")));
    // Same TDS mode as the installed legacy connector on this private test LAN.
    config.encryption(tiberius::EncryptionLevel::NotSupported);
    let tcp = TcpStream::connect(config.get_addr()).await?;
    let mut client = Client::connect(config, tcp.compat_write()).await?;
    let warehouses = request["warehouses"].as_array().ok_or("Faltan almacenes")?;
    if warehouses.is_empty() { return Err("Almacenes vacios".into()); }
    let mut clauses = vec![];
    for w in warehouses { let s = w.as_str().ok_or("Almacen invalido")?;
        if s.is_empty() || !s.chars().all(|c| c.is_ascii_alphanumeric()) { return Err("Almacen invalido".into()); }
        clauses.push(format!("'{}'", s));
    }
    let sql = format!("SELECT TRIM(p.productoid) AS erp_id, TRIM(hp.referencia) AS reference,
      TRIM(p.barras) AS ean, TRIM(p.barras2) AS ean2, TRIM(p.Barras3) AS ean3,
      TRIM(hp.nombre) AS name, TRIM(COALESCE(hp.nombrrefer,'')) AS short_name,
      TRIM(hp.unidad) AS unit, TRIM(COALESCE(hp.ManejPrese,'')) AS manages,
      CAST(p.valor AS VARCHAR(40)) AS gross, CAST(hp.ivaid AS VARCHAR(40)) AS tax,
      CAST(hp.PUMContenidoInterno AS VARCHAR(40)) AS content,
      TRIM(hp.PUMUnidadMedida) AS content_unit,
      CAST(COALESCE(s.qty,0) AS VARCHAR(40)) AS qty
      FROM Producto p JOIN HeadProd hp ON hp.headprodid=p.headprodid
      LEFT JOIN (SELECT productoid, SUM(invenactua) AS qty FROM InveProd
      WHERE almacenid IN ({}) GROUP BY productoid) s ON s.productoid=p.productoid", clauses.join(","));
    let mut products = select(&mut client, &sql).await?;
    let price_lists = select(&mut client, "SELECT TRIM(lp.ProductoId) AS erp_id, CAST(lp.Lista AS VARCHAR(20)) AS list_id, CAST(lp.Valor AS VARCHAR(40)) AS gross FROM ListaPrecio lp ORDER BY lp.ProductoId, lp.Lista, lp.Valor").await?;
    let mut primary_index: HashMap<String, Vec<&Value>> = HashMap::new();
    for r in &price_lists { if string(r,"list_id")=="1" { primary_index.entry(string(r,"erp_id").into()).or_default().push(r); } }
    for p in &mut products {
        let empty=vec![];
        let primary = primary_index.get(string(p,"erp_id")).unwrap_or(&empty);
        if string(p,"gross").is_empty() && primary.len()==1 {
            p["gross"]=primary[0]["gross"].clone(); p["price_source"]=json!("ListaPrecio.Lista=1");
        } else { p["price_source"]=json!(if primary.len()>1 && string(p,"gross").is_empty() {"AMBIGUOUS_LIST_1"} else {"Producto.valor"}); }
    }
    // Include factor=1: its price may differ, or it may be a redundant Caja/Paquete.
    let presentations = select(&mut client, "SELECT TRIM(p.productoid) AS erp_id,
      CAST(pr.PresentacionId AS VARCHAR(40)) AS presentation_id, TRIM(pr.Nombre) AS label,
      CAST(pr.Factor AS VARCHAR(40)) AS factor, CAST(pr.Valor AS VARCHAR(40)) AS gross,
      CAST(pr.PrecioDesdePrincipal AS VARCHAR(10)) AS from_main
      FROM Producto p JOIN HeadProd hp ON hp.headprodid=p.headprodid
      JOIN Presentacion pr ON pr.HeadProdId=hp.headprodid
      WHERE COALESCE(hp.ManejPrese,'')='S' AND pr.Estado='A' AND pr.Venta=1
      ORDER BY p.productoid, pr.PresentacionId").await?;
    let schema = select(&mut client, "SELECT TABLE_NAME AS table_name, COLUMN_NAME AS column_name,
      DATA_TYPE AS data_type FROM INFORMATION_SCHEMA.COLUMNS
      WHERE TABLE_NAME IN ('Producto','HeadProd','Presentacion','InveProd')
      ORDER BY TABLE_NAME, ORDINAL_POSITION").await?;
    let mut factors = serde_json::Map::new();
    // Preserve the previous single-presentation package parser verbatim.
    let mut index: HashMap<String,Vec<&Value>> = HashMap::new();
    for erp in &products {
        for k in ["erp_id", "reference", "ean", "ean2", "ean3"] {
            let value=legacy::normalize_reference(string(erp,k));
            if !value.is_empty() { index.entry(value).or_default().push(erp); }
        }
    }
    for ps in request["products"].as_array().ok_or("Faltan productos")? {
        let mut candidates: HashMap<String,&Value> = HashMap::new();
        for k in ["reference", "ean13"] {
            if let Some(matches)=index.get(&legacy::normalize_reference(string(ps,k))) {
                for erp in matches { candidates.insert(string(erp,"erp_id").into(),erp); }
            }
        }
        for erp in candidates.values() {
            let reference = legacy::normalize_reference(string(ps,"reference"));
            let ean = string(ps,"ean13");
            let keys = ["erp_id", "reference", "ean", "ean2", "ean3"];
            let matches = keys.iter().any(|k| !reference.is_empty() && legacy::normalize_reference(string(erp,k))==reference)
                || ["ean","ean2","ean3"].iter().any(|k| !ean.is_empty() && string(erp,k)==ean);
            if !matches { continue; }
            let unit = string(erp,"unit");
            let mut ps_content = legacy::parse_package_content(string(ps,"name"), unit);
            let erp_name = if string(erp,"manages")=="S" || string(erp,"short_name").is_empty() { string(erp,"name") } else { string(erp,"short_name") };
            let erp_content = legacy::parse_package_content(erp_name, unit);
            if let (Some(total),Some((erp_total,ref u))) = (legacy::parse_additive_unit_total(string(ps,"name")),erp_content.as_ref().cloned()) {
                if u=="und" && (total-erp_total).abs()<0.000001 { ps_content=Some((total,"und".into())); }
            }
            let mut factor=1.0;
            if let Some((ps_total,ps_unit))=ps_content {
                if legacy::normalize_unit(unit)=="KG" { factor=ps_total/erp_content.map(|v|v.0).unwrap_or(1000.0); }
                else if let Some((erp_total,erp_unit))=erp_content { if ps_unit==erp_unit { factor=ps_total/erp_total; } }
            }
            if !factor.is_finite() || factor<=0.0 { factor=1.0; }
            factors.insert(format!("{}:{}",ps["id"],string(erp,"erp_id")),json!(format!("{:.12}",factor)));
        }
    }
    println!("{}",json!({"host":host,"products":products,"presentations":presentations,"schema":schema,"legacy_factors":factors,"warehouses":warehouses,"price_lists":price_lists}));
    Ok(())
}
