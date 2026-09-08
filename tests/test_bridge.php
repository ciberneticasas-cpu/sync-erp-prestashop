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
    public $id, $price, $active, $cache_default_attribute, $name;
    public function __construct($id, ...$rest) {
        $this->id = $id;
        foreach (Memory::$products[$id] as $key=>$value) { $this->$key = $value; }
    }
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
    public $id, $id_product, $price, $reference, $minimal_quantity, $ean13, $default_on, $images;
    public function __construct($id = null, ...$rest) {
        $this->id = $id;
        if ($id) { foreach (Memory::$combos[$id] as $key=>$value) { $this->$key=$value; } }
    }
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
Memory::$products[7159]=['price'=>'48000', 'active'=>true, 'cache_default_attribute'=>142, 'name'=>[1=>'Eutarpan']];
Memory::$combos[142]=['id'=>142, 'id_product'=>7159, 'price'=>0, 'reference'=>'26074', 'minimal_quantity'=>1, 'images'=>[90]];
Memory::$combos[143]=['id'=>143, 'id_product'=>7159, 'price'=>43200, 'reference'=>'26074', 'minimal_quantity'=>1, 'images'=>[91]];
$op=['id'=>7159, 'base_price'=>'48000', 'mode'=>'presentations', 'stage_disabled'=>true, 'new_name'=>'', 'presentations'=>[
    ['combination_id'=>142, 'impact'=>'0', 'net_price'=>'48000', 'reference'=>'026074:BASE', 'label'=>'Caja', 'default'=>true, 'quantity'=>null],
    ['combination_id'=>143, 'impact'=>'-43200', 'net_price'=>'4800', 'reference'=>'026074:1414', 'label'=>'Sobre', 'default'=>false, 'quantity'=>null],
]];
$result=applyProduct($op);
check($result['verification']['prices'][1]['visible_price']===4800.0, 'Impacto Eutarpan incorrecto');
check(Memory::$combos[143]['images']===[91] && Memory::$associations===0, 'No debe borrar imagenes/asociaciones existentes');
check(!Memory::$products[7159]['active'], 'Presentaciones deben quedar en borrador');
echo "OK: actualizacion nativa y preservacion de imagenes\n";

Memory::$products[4520]=['price'=>'37350', 'active'=>true, 'cache_default_attribute'=>0, 'name'=>[1=>'Fraccion']];
$new=$op; $new['id']=4520; $new['base_price']='37350'; $new['new_name']='Ketoprofeno Caja / Blister';
$new['presentations'][0]=array_merge($op['presentations'][0], ['combination_id'=>0, 'net_price'=>'37350', 'reference'=>'000977:BASE', 'quantity'=>0]);
$new['presentations'][1]=array_merge($op['presentations'][1], ['combination_id'=>0, 'net_price'=>'12450', 'impact'=>'-24900', 'reference'=>'000977:779', 'label'=>'Blister', 'quantity'=>0]);
$result=applyProduct($new);
check(Memory::$associations===2, 'Debe crear dos asociaciones');
check(count(Memory::$attrs)===2, 'Debe reutilizar grupo y crear valores');
check(Memory::$products[4520]['cache_default_attribute']===200, 'Predeterminada incorrecta');
check(Memory::$stocks['4520:201']===0, 'No debe copiar inventario compartido');
echo "OK: creacion de combinaciones, atributos, predeterminada y stock inicial\n";

Memory::$badEngine=true;
$before=Memory::$products[7159]; $bad=$op; $bad['base_price']='49000';
try { applyProduct($bad); throw new Exception('Debio fallar validacion'); }
catch (RuntimeException $expected) { check(Memory::$products[7159]===$before, 'Debe revertir el producto al fallar la validacion'); }
echo "OK: rollback ante discrepancia del motor de precios\n";
Memory::$badEngine=false;

Memory::$products[1]=['price'=>'100', 'active'=>true, 'cache_default_attribute'=>0, 'name'=>[1=>'Simple']];
$simple=['id'=>1, 'base_price'=>'110', 'mode'=>'simple', 'stage_disabled'=>false, 'new_name'=>'', 'presentations'=>[
    ['combination_id'=>0, 'impact'=>'0', 'net_price'=>'110', 'reference'=>'1', 'default'=>true, 'quantity'=>null],
]];
$count=count(Memory::$combos); applyProduct($simple);
check(count(Memory::$combos)===$count && Memory::$products[1]['active'], 'Precio simple no debe convertir producto ni desactivarlo');
echo "OK: actualizacion de precio simple\n";
