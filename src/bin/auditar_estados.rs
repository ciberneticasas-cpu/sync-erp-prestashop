//! SQL Server reader. No general SQL executor, no write or production fallback.
#![allow(dead_code)]

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
    let catalog = select(&mut client, "SELECT TRIM(p.productoid) AS erp_id, CAST(p.headprodid AS VARCHAR(30)) AS headprod_id,
      CAST(p.tallaid AS VARCHAR(30)) AS talla_id, CAST(p.colorid AS VARCHAR(30)) AS color_id, TRIM(p.estado) AS estado, TRIM(hp.referencia) AS referencia, TRIM(hp.nombre) AS nombre,
      TRIM(hp.nombrrefer) AS nombre_corto, TRIM(p.barras) AS ean, TRIM(p.barras2) AS ean2, TRIM(p.Barras3) AS ean3,
      TRIM(hp.EsObsequio) AS es_obsequio, TRIM(hp.ProductoObsequio) AS producto_obsequio, CAST(hp.HeadProdInterno AS VARCHAR(30)) AS producto_interno, TRIM(hp.NoFacturarEnFM) AS no_facturar_fm, TRIM(hp.sustituto) AS sustituto, TRIM(hp.Observacion) AS observacion,
      TRIM(hp.ECommerce) AS ecommerce, TRIM(hp.tipoproductoid) AS tipo_producto,
      TRIM(hp.Tipo) AS tipo, TRIM(hp.familia) AS familia, TRIM(hp.ClasificacionId) AS clasificacion,
      TRIM(hp.grupoi) AS grupo1, TRIM(hp.grupoii) AS grupo2, TRIM(hp.grupoiii) AS grupo3,
      TRIM(hp.unidad) AS unidad, TRIM(hp.ManejPrese) AS maneja_presentaciones,
      CAST(p.valor AS VARCHAR(40)) AS precio_producto,
      CONVERT(VARCHAR(30),p.fechaventa,126) AS ultima_venta,
      CONVERT(VARCHAR(30),hp.ultimcompr,126) AS ultima_compra,
      CONVERT(VARCHAR(30),p.FechaModif,126) AS modificacion_producto,
      CONVERT(VARCHAR(30),hp.fechamodif,126) AS modificacion_cabecera,
      CONVERT(VARCHAR(30),hp.fechacreac,126) AS creacion,
      CAST(COALESCE(i.stock,0) AS VARCHAR(40)) AS stock_todos_almacenes
      FROM Producto p JOIN HeadProd hp ON hp.headprodid=p.headprodid
      LEFT JOIN (SELECT productoid,SUM(invenactua) AS stock FROM InveProd GROUP BY productoid) i ON i.productoid=p.productoid
      ORDER BY p.productoid").await?;
    let schema = select(&mut client, "SELECT TABLE_SCHEMA AS esquema,TABLE_NAME AS tabla,COLUMN_NAME AS campo,DATA_TYPE AS tipo
      FROM INFORMATION_SCHEMA.COLUMNS WHERE (TABLE_NAME IN ('Producto','HeadProd','Presentacion')) OR
      ((TABLE_NAME LIKE '%Prod%' OR TABLE_NAME LIKE '%Estad%' OR TABLE_NAME LIKE '%Clasif%') AND
       (COLUMN_NAME LIKE '%estad%' OR COLUMN_NAME LIKE '%activ%' OR COLUMN_NAME LIKE '%descont%' OR COLUMN_NAME LIKE '%baja%' OR COLUMN_NAME LIKE '%bloque%' OR COLUMN_NAME LIKE '%venta%'))
      ORDER BY TABLE_NAME,ORDINAL_POSITION").await?;
    let constraints = select(&mut client, "SELECT OBJECT_NAME(parent_object_id) AS tabla,name AS restriccion,definition AS definicion
      FROM sys.check_constraints WHERE OBJECT_NAME(parent_object_id) IN ('Producto','HeadProd','Presentacion')").await?;
    let relations = select(&mut client, "SELECT OBJECT_NAME(f.parent_object_id) AS tabla,COL_NAME(f.parent_object_id,f.parent_column_id) AS campo,
      OBJECT_NAME(f.referenced_object_id) AS tabla_referida,COL_NAME(f.referenced_object_id,f.referenced_column_id) AS campo_referido
      FROM sys.foreign_key_columns f WHERE OBJECT_NAME(f.parent_object_id) IN ('Producto','HeadProd')").await?;
    let descriptions = select(&mut client, "SELECT OBJECT_NAME(ep.major_id) AS tabla,COL_NAME(ep.major_id,ep.minor_id) AS campo,
      CAST(ep.value AS NVARCHAR(4000)) AS descripcion FROM sys.extended_properties ep
      WHERE ep.class=1 AND OBJECT_NAME(ep.major_id) IN ('Producto','HeadProd','Presentacion')").await?;
    let sizes = select(&mut client, "SELECT CAST((SELECT t.* FROM Talla t WHERE t.tallaid IN
      (SELECT tallaid FROM Producto WHERE headprodid IN (SELECT headprodid FROM Producto WHERE productoid IN ('008761','030947')))
      FOR JSON PATH) AS NVARCHAR(MAX)) AS contenido").await?;
    let types = select(&mut client, "SELECT CAST((SELECT * FROM TipoProducto FOR JSON PATH) AS NVARCHAR(MAX)) AS contenido").await?;
    println!("{}",json!({"host":host,"catalog":catalog,"schema":schema,"constraints":constraints,"relations":relations,"descriptions":descriptions,"product_types":types,"glade_sizes":sizes}));
    Ok(())
}
