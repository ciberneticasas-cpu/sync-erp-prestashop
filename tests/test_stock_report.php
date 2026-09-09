<?php
declare(strict_types=1);
define('_DB_PREFIX_', 'ps_');
function demand($v, $message) { if (!$v) throw new RuntimeException($message); }
class Configuration {
    public static $values = ['STOCKTHRESHOLDHIDE_ENABLED'=>1, 'STOCKTHRESHOLDHIDE_CATEGORY_MODE'=>'rules', 'STOCKTHRESHOLDHIDE_BLOCK_PRODUCT_PAGE'=>1, 'STOCKTHRESHOLDHIDE_MIN_QTY'=>3];
    public static function get($key) { return self::$values[$key] ?? null; }
}
class Module {
    public static $enabled = true;
    public static function isEnabled($name) { return self::$enabled; }
    public static function getInstanceByName($name) { return new StockModule(); }
}
class StockModule {
    protected function getCategoryRules() { return [['id_category'=>20,'min_qty'=>5],['id_category'=>21,'min_qty'=>1]]; }
    protected function getEffectiveRuleCategoryIds($rule) { return $rule['id_category'] == 20 ? [20,22] : [21]; }
    protected function getEffectiveSelectedCategoryIds() { return [20,22]; }
    protected function getProductTotalQuantityFromDatabase($id) { return $id == 4 ? 6 : 0; }
}
class StockAvailable {
    public static $qty = [1=>4,2=>5,3=>0,4=>0,5=>0];
    public static function getQuantityAvailableByProduct($id, $attribute, $shop) { return self::$qty[$id]; }
}
class Db {
    public static function getInstance() { return new self(); }
    public function executeS($sql) { return [['id_product'=>1,'id_category'=>22],['id_product'=>1,'id_category'=>21],['id_product'=>2,'id_category'=>20],['id_product'=>4,'id_category'=>20],['id_product'=>5,'id_category'=>21]]; }
}
require __DIR__.'/../stock_informe.php';
$products = array_map(function($id) { return ['id'=>$id]; }, range(1,5));
$v=stockVisibility($products);
demand($v[1]['hidden'] && $v[1]['minimum']===5 && $v[1]['page_blocked'], 'Subcategoria y mayor minimo');
demand(!$v[2]['hidden'], 'Igual al minimo no se oculta');
demand(!$v[3]['hidden'] && $v[3]['reason']==='SIN_REGLA_APLICABLE', 'Sin regla no ocultar stock cero');
demand(!$v[4]['hidden'] && $v[4]['quantity']===6, 'Fallback de stock como modulo');
demand($v[5]['hidden'] && $v[5]['minimum']===1, 'Regla minimo uno');
Configuration::$values['STOCKTHRESHOLDHIDE_BLOCK_PRODUCT_PAGE']=0;
$v=stockVisibility($products);demand($v[1]['hidden'] && !$v[1]['page_blocked'], 'Ocultamiento listado distinto de bloqueo URL');
Configuration::$values['STOCKTHRESHOLDHIDE_CATEGORY_MODE']='selected';
$v=stockVisibility($products);demand(!$v[1]['hidden'] && $v[1]['minimum']===3 && !$v[5]['hidden'], 'Seleccion de categorias');
Configuration::$values['STOCKTHRESHOLDHIDE_CATEGORY_MODE']='all';
$v=stockVisibility($products);demand($v[3]['hidden'], 'Toda tienda');
Module::$enabled=false;
$v=stockVisibility($products);demand(!$v[1]['hidden'] && $v[1]['reason']==='MODULO_DESACTIVADO', 'Modulo desactivado');
echo "OK: reglas, subcategorias, minimo mas exigente, fallback, bloqueo y modulo desactivado\n";
