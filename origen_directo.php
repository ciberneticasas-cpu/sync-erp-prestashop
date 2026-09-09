<?php
/** Runs only on the test host. Remote MariaDB accepts reads through this adapter. */
declare(strict_types=1);
define('MERCABOY_LIBRARY_ONLY', true);
require __DIR__ . '/bridge.php';

function assertSourceSelect(string $sql): void {
    demand((bool)preg_match('/^\s*(?:EXPLAIN\s+)?SELECT\b/i', $sql), 'ORIGEN: SQL distinto de SELECT rechazado');
    demand(!preg_match('/;|\/\*|--|\b(INTO|OUTFILE|DUMPFILE|FOR\s+UPDATE|LOCK\s+IN|GET_LOCK|RELEASE_LOCK|SLEEP|BENCHMARK|LOAD_FILE)\b/i', $sql), 'ORIGEN: SQL no permitido');
}
class SourceConnection extends mysqli {
    public array $counts = [], $tableCounts = [];
    public function query(string $query, int $result_mode = MYSQLI_STORE_RESULT): mysqli_result|bool {
        $sql = trim($query);
        if ($sql === 'START TRANSACTION READ ONLY') {
            $sql = 'START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY';
            $kind = 'BEGIN_READ_ONLY';
        } else {
            assertSourceSelect($sql);
            $kind = stripos($sql, 'EXPLAIN') === 0 ? 'EXPLAIN_SELECT' : 'SELECT';
        }
        $this->counts[$kind] = ($this->counts[$kind] ?? 0) + 1;
        preg_match_all('/(?:FROM|JOIN)\s+`?(ps_\w+)/i',$sql,$tables);
        foreach (array_unique($tables[1]) as $table) { $this->tableCounts[$table]=($this->tableCounts[$table] ?? 0)+1; }
        return parent::query($sql, $result_mode);
    }
    public function commit(int $flags = 0, ?string $name = null): bool {
        // Keep snapshot() and native prices in the same transaction. Finish by rollback.
        return true;
    }
    public function enableReadOnly(): void {
        parent::query('SET SESSION TRANSACTION READ ONLY');
        demand((int)$this->query('SELECT @@session.tx_read_only')->fetch_row()[0] === 1, 'ORIGEN: sesion no es de lectura');
    }
    public function privileges(): array {
        $result = [];
        foreach (parent::query('SHOW GRANTS')->fetch_all(MYSQLI_NUM) as $row) {
            if (preg_match('/^GRANT (.*?) ON (.*?) TO /', $row[0], $m)) {
                $result[] = ['privileges'=>$m[1], 'scope'=>$m[2]];
            } else { $result[] = ['other_grant'=>true]; }
        }
        $this->counts['SHOW_GRANTS'] = 1;
        return $result;
    }
}
class PendingSourceQuery extends RuntimeException {}

function sourceNativePrices(SourceConnection $conn, array $snapshot, string $prefix, bool $batch = true): array {
    // Load classes only: never config.inc.php, remote PHP, kernel, sessions or modules.
    require '/var/www/html/config/defines.inc.php';
    foreach (['_DB_PREFIX_'=>$prefix, '_DB_NAME_'=>'mercaboy_2024', '_DB_SERVER_'=>'READ_ONLY_ADAPTER_REQUIRED',
              '_DB_USER_'=>'', '_DB_PASSWD_'=>'', '_PS_CACHE_ENABLED_'=>false, '_PS_CACHING_SYSTEM_'=>'CacheFs',
              '_PS_CREATION_DATE_'=>'2020-01-01'] as $key=>$value) { define($key, $value); }
    require '/var/www/html/config/autoload.php';
    demand(_PS_VERSION_ === '8.1.7', 'ORIGEN: motor local incompatible');
    $hooks = $conn->query("SELECT DISTINCT h.name FROM {$prefix}hook h JOIN {$prefix}hook_module hm ON hm.id_hook=h.id_hook JOIN {$prefix}module m ON m.id_module=hm.id_module WHERE hm.id_shop=1 AND m.active=1")->fetch_all(MYSQLI_ASSOC);
    $GLOBALS['source_active_hooks'] = array_map('strtolower', array_column($hooks, 'name'));
    // Never execute module code. A relevant active hook requires explicit review.
    class Hook {
        public static function exec($name, ...$args) {
            demand(!in_array(strtolower($name), $GLOBALS['source_active_hooks'], true), 'ORIGEN: hook activo requiere revision: '.$name);
            return null;
        }
        public static function getIdByName($name) { self::exec($name); return 0; }
        public static function getModulesFromHook($id) { return []; }
    }
    class SourcePriceDb extends DbMySQLi {
        public bool $collect = false;
        public array $pending = [], $answers = [];
        public function __construct($connection) { $this->link=$connection; $this->is_cache_enabled=false; }
        public function connect() { throw new RuntimeException('ORIGEN: conexion alternativa rechazada'); }
        public function disconnect() {}
        protected function _query($sql) { return $this->link->query($sql); }
        public function getRow($sql, $use_cache = true) {
            $sql = (string)$sql;
            if (strpos($sql, 'AS `score`') !== false && strpos($sql, '`'._DB_PREFIX_.'specific_price`') !== false) {
                if (array_key_exists($sql, $this->answers)) { return $this->answers[$sql]; }
                if ($this->collect) { $this->pending[$sql]=true; throw new PendingSourceQuery(); }
            }
            return parent::getRow($sql, $use_cache);
        }
        public function fetchPending(): void {
            // Exact native SELECTs, grouped in one network round trip per 100 queries.
            foreach (array_chunk(array_keys($this->pending), 100) as $queries) {
                $parts=[];
                foreach ($queries as $i=>$sql) {
                    assertSourceSelect($sql);
                    $this->answers[$sql]=false;
                    $parts[]='SELECT '.$i.' AS __source_key, q.* FROM ('.$sql.' LIMIT 1) q';
                }
                foreach ($this->link->query(implode(' UNION ALL ', $parts))->fetch_all(MYSQLI_ASSOC) as $row) {
                    $sql=$queries[(int)$row['__source_key']]; unset($row['__source_key']); $this->answers[$sql]=$row;
                }
            }
            $this->collect=false;
        }
    }
    $db=new SourcePriceDb($conn); Db::$instance=[$db]; Db::$_servers=[['server'=>'READ_ONLY_ADAPTER_REQUIRED']]; Db::$_slave_servers_loaded=true;
    PrestaShop\PrestaShop\Adapter\ServiceLocator::setServiceContainerInstance((new PrestaShop\PrestaShop\Core\ContainerBuilder())->build());
    Shop::setContext(Shop::CONTEXT_SHOP, 1);
    $context=Context::getContext(); $context->shop=new Shop(1);
    date_default_timezone_set(Configuration::get('PS_TIMEZONE') ?: 'America/Bogota');
    $context->language=new Language((int)Configuration::get('PS_LANG_DEFAULT'));
    $context->currency=new Currency((int)Configuration::get('PS_CURRENCY_DEFAULT'));
    $context->country=new Country((int)Configuration::get('PS_COUNTRY_DEFAULT'));
    $context->customer=new Customer(); $context->cart=new Cart();
    $context->cart->id_shop=1; $context->cart->id_currency=$context->currency->id; $context->cart->id_lang=$context->language->id;
    $set = function ($class, $name, $value) { $p=new ReflectionProperty($class,$name); $p->setAccessible(true); $p->setValue(null,$value); };
    // Bulk reads populate the native in-memory caches without changing their semantics.
    $taxes=[]; $values=[]; $possible=[]; $priority=[]; $reductions=[]; $items=[];
    $group=(int)Configuration::get('PS_UNIDENTIFIED_GROUP');
    foreach ($snapshot['products'] as $p) {
        $pid=$p['id']; $taxes[$pid]=(int)$p['id_tax_rules_group'];
        $possible[$pid]=false; $priority[$pid]=false; $reductions[$pid.'-'.$group]=false;
        $items[]=[$pid,0]; foreach ($p['combinations'] as $c) { $items[]=[$pid,$c['id']]; }
    }
    $rows=$conn->query("SELECT p.id_product, p.price, p.ecotax, a.id_product_attribute, a.price AS attribute_price, a.ecotax AS attribute_ecotax, a.default_on FROM {$prefix}product_shop p LEFT JOIN {$prefix}product_attribute_shop a ON a.id_product=p.id_product AND a.id_shop=p.id_shop WHERE p.id_shop=1")->fetch_all(MYSQLI_ASSOC);
    foreach ($rows as $r) {
        $value=['price'=>$r['price'],'ecotax'=>$r['ecotax'],'attribute_price'=>$r['attribute_price'],'attribute_ecotax'=>$r['attribute_ecotax']];
        $values[$r['id_product'].'-1'][(int)$r['id_product_attribute']]=$value;
        if ((int)$r['default_on']===1) { $values[$r['id_product'].'-1'][0]=$value; }
    }
    $set('ProductCore','_pricesLevel2',$values);
    foreach ($snapshot['products'] as $p) { foreach ($p['specific_prices'] as $r) { $possible[$p['id']]=true; } }
    $global=(bool)$conn->query("SELECT 1 FROM {$prefix}specific_price WHERE id_product=0 LIMIT 1")->fetch_row();
    $set('SpecificPriceCore','_hasGlobalProductRules',$global); $set('SpecificPriceCore','_couldHaveSpecificPriceCache',$possible);
    foreach ($conn->query("SELECT id_product, priority FROM {$prefix}specific_price_priority ORDER BY id_specific_price_priority")->fetch_all(MYSQLI_ASSOC) as $r) { $priority[(int)$r['id_product']]=$r['priority']; }
    $set('SpecificPriceCore','_cache_priorities',$priority);
    foreach ($conn->query("SELECT id_product,id_group,reduction FROM {$prefix}product_group_reduction_cache")->fetch_all(MYSQLI_ASSOC) as $r) { $reductions[$r['id_product'].'-'.$r['id_group']]=$r['reduction']; }
    $set('GroupReductionCore','reduction_cache',$reductions);
    if ($batch) {
        $db->collect=true;
        foreach ($items as [$pid,$cid]) { Cache::store('product_id_tax_rules_group_'.$pid.'_1',$taxes[$pid]); try { Product::getPriceStatic($pid,true,$cid ?: false,6); } catch (PendingSourceQuery $e) {} }
        $db->fetchPending();
    }
    if (!$batch) {
        // Validation path: original engine queries, without preloaded price caches.
        $set('ProductCore','_pricesLevel2',[]);
        $set('SpecificPriceCore','_couldHaveSpecificPriceCache',[]);
        $set('SpecificPriceCore','_cache_priorities',[]);
        $set('SpecificPriceCore','_hasGlobalProductRules',null);
        $set('GroupReductionCore','reduction_cache',[]);
        Cache::clean('product_id_tax_rules_group_*');
    }
    $prices=[];
    foreach ($items as [$pid,$cid]) {
        if ($batch) { Cache::store('product_id_tax_rules_group_'.$pid.'_1',$taxes[$pid]); }
        $value=Product::getPriceStatic($pid,true,$cid ?: false,6);
        demand($value !== null && is_finite((float)$value), 'ORIGEN: precio no calculable: '.$pid.':'.$cid);
        $prices[]=['id'=>$pid,'combination_id'=>$cid,'actual'=>$value,'proposed'=>$value];
    }
    return ['host'=>'www.mercaboy.com','context'=>'Motor local 8.1.7, SELECT directo al origen, visitante sin sesion, cantidad 1',
        'prices'=>$prices,'currency'=>['iso_code'=>$context->currency->iso_code,'precision'=>(int)$context->currency->precision,'round_mode'=>(int)Configuration::get('PS_PRICE_ROUND_MODE')]];
}

if (defined('SOURCE_LIBRARY_ONLY')) { return; }
try {
    $request=json_decode(stream_get_contents(STDIN),true,512,JSON_THROW_ON_ERROR);
    localParameters($request); // Validates the LOCAL test host and its protected database.
    demand(($request['SERVIDOR_CONGELADO'] ?? '') === 'www.mercaboy.com', 'ORIGEN no permitido');
    $e=envValues($request['baseline_env_file'] ?? '');
    demand(($e['MARIADB_HOST'] ?? '') === 'www.mercaboy.com' && ($e['MARIADB_DATABASE'] ?? '') === 'mercaboy_2024', 'ORIGEN: credenciales de otro servidor/base');
    $prefix=$e['DB_PREFIX'] ?? 'ps_'; demand($prefix === 'ps_', 'ORIGEN: prefijo incompatible');
    mysqli_report(MYSQLI_REPORT_ERROR | MYSQLI_REPORT_STRICT);
    $conn=new SourceConnection(); $conn->options(MYSQLI_OPT_CONNECT_TIMEOUT,8);
    $conn->real_connect($e['MARIADB_HOST'],$e['MARIADB_USER'],$e['MARIADB_PASSWORD'],$e['MARIADB_DATABASE'],(int)($e['MARIADB_PORT'] ?? 3306));
    $conn->set_charset('utf8mb4'); $conn->enableReadOnly();
    $shops=$conn->query("SELECT id_shop,domain,domain_ssl FROM {$prefix}shop_url")->fetch_all(MYSQLI_ASSOC);
    demand(count($shops)===1 && $shops[0]['domain']==='www.mercaboy.com' && $shops[0]['domain_ssl']==='www.mercaboy.com' && (int)$shops[0]['id_shop']===1, 'ORIGEN: tienda inesperada');
    $version=$conn->query("SELECT value FROM {$prefix}configuration WHERE name='PS_VERSION_DB' LIMIT 1")->fetch_row()[0];
    demand($version==='8.1.7','ORIGEN: version incompatible');
    $grants=$conn->privileges();
    $result=snapshot($conn,['database_prefix'=>$prefix],$request['ids'] ?? []);
    $result['target']='www.mercaboy.com/mercaboy_2024/1';
    $result['source_prices']=sourceNativePrices($conn,$result,$prefix,empty($request['native_unbatched']));
    demand((int)$conn->query('SELECT @@session.tx_read_only')->fetch_row()[0]===1,'ORIGEN: cambio de modo de lectura');
    $result['read_only_evidence']=['session_read_only'=>true,'transaction'=>'CONSISTENT SNAPSHOT READ ONLY',
        'queries'=>$conn->counts,'query_tables'=>$conn->tableCounts,'transport'=>'mysql_direct_same_as_ConsultaMariaDB','tls'=>false,'account_grants'=>$grants,
        'remote_php_executed'=>false,'source_writes_executed'=>0];
    $conn->rollback();
    echo json_encode($result,JSON_UNESCAPED_UNICODE | JSON_THROW_ON_ERROR)."\n";
} catch (Throwable $e) {
    if (isset($conn)) { try { $conn->rollback(); } catch (Throwable $ignored) {} }
    fwrite(STDERR,'ORIGEN_LECTURA_FALLIDA: '.$e->getMessage()."\n"); exit(1);
}
