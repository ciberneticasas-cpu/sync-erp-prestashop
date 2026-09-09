<?php
/** Contract tests with in-memory doubles: no PrestaShop bootstrap or database. */
declare(strict_types=1);
define('MERCABOY_LIBRARY_ONLY', true);
class Memory {
    public static array $products = [], $combos = [], $stocks = [], $attrs = [];
    public static bool $badEngine = false;
    public static int $next = 200, $associations = 0;
}
class Db {
    private array $before = [];
    public static function getInstance(): self { static $db; return $db ?? ($db = new self()); }
    public function execute(string $sql): bool {
        if ($sql === 'START TRANSACTION') { $this->before = [Memory::$products, Memory::$combos, Memory::$stocks]; }
        elseif ($sql === 'ROLLBACK') { [Memory::$products, Memory::$combos, Memory::$stocks] = $this->before; }
        elseif ($sql !== 'COMMIT') { throw new RuntimeException('SQL de catalogo prohibido en el adaptador'); }
        return true;
    }
}
class Product {
    public $unit_price = 0, $unity = '', $unit_price_ratio = 0;
    public $id, $price, $active, $cache_default_attribute, $name;
    public function __construct($id, ...$rest) {
        $this->id = $id;
        foreach (Memory::$products[$id] as $key=>$value) { $this->$key = $value; }
    }
    public function setFieldsToUpdate(array $fields): void { if (array_diff(array_keys($fields), ['price','unity','unit_price'])) { throw new RuntimeException('Solo precio/PUM'); } }
    public function update(): bool { Memory::$products[$this->id] = get_object_vars($this); return true; }
    public function deleteDefaultAttributes(): bool {
        foreach (Memory::$combos as &$combo) { if ($combo['id_product'] === $this->id) { $combo['default_on'] = null; } }
        return true;
    }
    public function setDefaultAttribute(int $id): bool {
        Memory::$combos[$id]['default_on'] = 1;
        Memory::$products[$this->id]['cache_default_attribute'] = $id;
        return true;
    }
    public static function flushPriceCache(): void {}
    public static function getPriceStatic($id, $tax, $combo, ...$args): float {
        if (Memory::$badEngine) { return 7.0; }
        return (float)Memory::$products[$id]['price'] + (float)(Memory::$combos[$combo]['price'] ?? 0);
    }
}
class Combination {
    public $unit_price_impact = 0;
    public $id, $id_product, $price, $reference, $minimal_quantity, $ean13, $default_on, $images;
    public function __construct($id = null, ...$rest) {
        $this->id = $id;
        if ($id) { foreach (Memory::$combos[$id] as $key=>$value) { $this->$key=$value; } }
    }
    public function setFieldsToUpdate(array $fields): void { if (array_diff(array_keys($fields), ['price','unit_price_impact'])) { throw new RuntimeException('Solo precio/PUM'); } }
    public function update(): bool { Memory::$combos[$this->id]=get_object_vars($this); return true; }
    public function add(): bool { $this->id=Memory::$next++; return $this->update(); }
    public function setAttributes($ids): bool { Memory::$associations++; Memory::$combos[$this->id]['attribute_ids']=$ids; return true; }
}
class StockAvailable {
    public static function getQuantityAvailableByProduct($p, $a, $shop): int { return Memory::$stocks["$p:$a"] ?? 0; }
    public static function setQuantity($p, $a, $q, $shop): void { Memory::$stocks["$p:$a"]=$q; }
    public static function setProductOutOfStock(...$args): void {}
}
class Validate { public static function isLoadedObject($object): bool { return isset(Memory::$products[$object->id]); } }
class Language { public static function getLanguages($active): array { return [['id_lang'=>1]]; } }
class Context {
    public static function getContext() { return (object)['currency'=>(object)['precision'=>0]]; }
}
class Tools {
    public static function ps_round($value,$precision) { return round($value,$precision,PHP_ROUND_HALF_UP); }
}
class Configuration { public static function get($key): int { return 1; } }
class AttributeGroup {
    public static function getAttributesGroups($lang): array { return [['name'=>'Presentación', 'id_attribute_group'=>13]]; }
    public static function getAttributes($lang, $group): array { return Memory::$attrs; }
}
class ProductAttribute {
    public $id, $id_attribute_group, $name;
    public function add(): bool {
        $this->id=count(Memory::$attrs)+50;
        Memory::$attrs[]=['id_attribute'=>$this->id, 'name'=>$this->name[1]];
        return true;
    }
}
require __DIR__ . '/../bridge.php';
function check(bool $condition, string $message): void { if (!$condition) { throw new Exception($message); } }
Memory::$products[1]=['price'=>'100', 'active'=>true, 'available_for_order'=>true, 'cache_default_attribute'=>142, 'name'=>[1=>'Nombre original']];
Memory::$combos[142]=['id'=>142,'id_product'=>1,'price'=>0,'reference'=>'caja','minimal_quantity'=>2,'default_on'=>1,'images'=>[90]];
Memory::$combos[143]=['id'=>143,'id_product'=>1,'price'=>-90,'reference'=>'blister','minimal_quantity'=>3,'default_on'=>null,'images'=>[91]];
Memory::$stocks=['1:0'=>10,'1:142'=>3,'1:143'=>7];
$op=['id'=>1,'base_price'=>'200','mode'=>'presentations','prices_only'=>true,'stage_disabled'=>false,'preview_only'=>false,'new_name'=>'','presentations'=>[
 ['combination_id'=>142,'impact'=>'0','net_price'=>'200','reference'=>'caja','default'=>true,'quantity'=>null],
 ['combination_id'=>143,'impact'=>'-180','net_price'=>'20','reference'=>'blister','default'=>false,'quantity'=>null]
]];
$stocks=Memory::$stocks;
$result=applyPrices($op);
check($result['verification']['prices'][1]['visible_price']===20.0,'Precio fraccion');
check(Memory::$stocks===$stocks && Memory::$associations===0 && count(Memory::$combos)===2,'No modificar stock/estructura');
check(Memory::$products[1]['active'] && Memory::$products[1]['available_for_order'] && Memory::$products[1]['name']===[1=>'Nombre original'],'Preservar publicacion/nombre');
check(Memory::$combos[143]['minimal_quantity']===3 && Memory::$combos[142]['default_on']===1 && Memory::$combos[143]['images']===[91],'Preservar combinaciones');
$bad=$op;$bad['prices_only']=false;
try { applyPrices($bad); throw new Exception('Debio bloquear estructura'); } catch(RuntimeException $expected) {}
$before=Memory::$products;Memory::$badEngine=true;$bad=$op;$bad['base_price']='300';
try { applyPrices($bad); throw new Exception('Debio fallar'); } catch(RuntimeException $expected) {check(Memory::$products===$before,'Rollback precio');}
echo "OK: precios, preservacion de estructura/stock/publicacion y rollback\n";

Memory::$badEngine=false;
$op['pum']=['unity'=>'Unidad','unit_price'=>'2','combinations'=>[
 ['combination_id'=>142,'ratio'=>'100','unit_price'=>'2','impact'=>'0'],
 ['combination_id'=>143,'ratio'=>'10','unit_price'=>'2','impact'=>'0']
]];
$result=applyPrices($op);
check($result['verification']['prices'][1]['unit_price_ratio']===10.0, 'Ratio de blister debe ser 10, no el ratio padre');
check($result['verification']['prices'][1]['unit_price']===2.0, 'PUM de blister');
check(Memory::$stocks===$stocks, 'PUM no cambia stock');
$before=[Memory::$products, Memory::$combos];
$bad=$op;$bad['pum']['unity']='Gramo';$bad['pum']['unit_price']='1';
$bad['pum']['combinations'][1]['impact']='1';Memory::$badEngine=true;
try { applyPrices($bad); throw new Exception('Debio fallar'); }
catch(RuntimeException $expected) {check([Memory::$products, Memory::$combos]===$before,'Rollback PUM padre y combinaciones');}
echo "OK: PUM por presentacion, cambios sin precio y rollback PUM\n";

Memory::$badEngine=false;
Memory::$products[2]=['price'=>'100','active'=>true,'available_for_order'=>true,'name'=>[1=>'Nombre conservado'],'unity'=>'Unidad','unit_price'=>'10'];
Memory::$combos[150]=['id'=>150,'id_product'=>2,'price'=>'999','unit_price_impact'=>0,'reference'=>'talla','minimal_quantity'=>1];
$initialImpact=['id'=>2,'before'=>['combinations'=>[['id'=>150,'price'=>'999','reference'=>'talla']]],'mode'=>'simple','prices_only'=>true,'stage_disabled'=>false,'preview_only'=>false,'new_name'=>'','base_price'=>'100',
 'presentations'=>[['combination_id'=>0,'impact'=>'0','net_price'=>'100','reference'=>'simple','quantity'=>null]],
 'combination_prices'=>[['combination_id'=>150,'impact'=>'20']],
 'pum'=>['unity'=>'Unidad','unit_price'=>'10','combinations'=>[['combination_id'=>150,'impact'=>'2','unit_price'=>'12','ratio'=>'10']]]];
$r=applyPrices($initialImpact);
check(Memory::$combos[150]['price']==='20','Impacto desde base congelada');
check($r['verification']['prices'][1]['net_price']===120.0,'Verificar impacto inicial aplicado');
check(Memory::$products[2]['name']===[1=>'Nombre conservado'],'Conservar nombre al restaurar impacto');
echo "OK: impacto inicial de variante y nombre conservado\n";

Memory::$badEngine=false;
foreach ([false, null, ''] as $inactive) {
    Memory::$products[1]['active']=$inactive;
    $before=[Memory::$products, Memory::$combos, Memory::$stocks];
    try { applyPrices($op); throw new Exception('Debio bloquear PS no activo'); }
    catch (RuntimeException $expected) {
        check(strpos($expected->getMessage(), 'no activo')!==false, 'Motivo de bloqueo');
        check([Memory::$products, Memory::$combos, Memory::$stocks]===$before, 'Inactivo sin escrituras');
    }
}
echo "OK: estado PS inactivo o nulo impide escrituras\n";

Memory::$products[1]['active']=true;
$before=[Memory::$products, Memory::$combos, Memory::$stocks];
$bad=$op;$bad['base_price']='200';unset($bad['pum']);
$bad['presentations'][0]['net_price']='200';$bad['presentations'][0]['impact']='0';
$bad['presentations'][1]['net_price']='199.999999';$bad['presentations'][1]['impact']='-0.000001';
try { applyPrices($bad); throw new Exception('Debio detectar precios visibles iguales'); }
catch(RuntimeException $expected) {
    check(strpos($expected->getMessage(),'iguales al redondear')!==false,'Comparacion segun moneda');
    check([Memory::$products, Memory::$combos, Memory::$stocks]===$before,'Rollback por precios iguales visibles');
}
echo "OK: precios de presentaciones comparados con precision de moneda\n";
