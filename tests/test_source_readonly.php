<?php
define('SOURCE_LIBRARY_ONLY',true);
require __DIR__.'/../origen_directo.php';
$accepted=['SELECT id_product FROM ps_product', 'EXPLAIN SELECT COUNT(*) FROM ps_specific_price', 'SELECT * FROM (SELECT 1 AS x) q UNION ALL SELECT * FROM (SELECT 2 AS x) q'];
foreach($accepted as $sql){assertSourceSelect($sql);}
// No connection is opened. Rejection must happen before mysqli can send any SQL.
$conn=new SourceConnection();
foreach(['UPDATE ps_product SET price=0','DELETE FROM ps_product','INSERT INTO ps_product VALUES (1)',
         'DROP TABLE ps_product','SET SESSION TRANSACTION READ WRITE','COMMIT',
         'SELECT 1; DELETE FROM ps_product','SELECT 1 INTO OUTFILE "/tmp/test"',
         'SELECT * FROM ps_product FOR UPDATE','SELECT GET_LOCK("test",1)',
         'SELECT 1 /*!50000 INTO OUTFILE "/tmp/test" */'] as $sql){
    try{$conn->query($sql);throw new Exception('SQL no rechazado');}
    catch(RuntimeException $e){demand(strpos($e->getMessage(),'ORIGEN:')===0,'Rechazo inesperado');}
}
configureFrozenHost(['SERVIDOR_CONGELADO'=>'www.mercaboy.com']);
define('TEST_HOST','www.mercaboy.com');
try{applyPrices([]);throw new Exception('Escritura productiva no rechazada');}
catch(RuntimeException $e){demand(strpos($e->getMessage(),'no admite escrituras')!==false,'Error inesperado');}
echo "OK: SQL de escritura rechazado antes de abrir conexion; produccion bloqueada como destino\n";
