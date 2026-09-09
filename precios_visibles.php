<?php
/** Read-only native prices and forecasts; only process-local price caches are changed. */
function visiblePrices(array $request): array {
    boot();
    $db = Db::getInstance();
    demand($db->execute('START TRANSACTION READ ONLY'), 'No inicio lectura de precios');
    try {
        $cache = new ReflectionProperty('ProductCore', '_pricesLevel2');
        $cache->setAccessible(true);
        $result = [];
        foreach ($request['products'] as $row) {
            $pid = (int)$row['id'];
            $ids = array_values(array_unique(array_merge([0], array_map('intval', $row['combinations']))));
            Product::flushPriceCache();
            $actual = [];
            foreach ($ids as $cid) {
                $value = Product::getPriceStatic($pid, true, $cid ?: false, 6);
                demand($value !== null && is_finite((float)$value), 'Precio visible no disponible');
                $actual[$cid] = $value;
            }
            $proposed = $actual;
            if (isset($row['proposal'])) {
                $proposal = $row['proposal'];
                $values = $cache->getValue();
                $key = $pid . '-1';
                demand(isset($values[$key]), 'Cache nativa de precios incompatible');
                foreach ($values[$key] as $cid => &$value) {
                    demand(array_key_exists('price', $value) && array_key_exists('attribute_price', $value), 'Formato de cache incompatible');
                    $value['price'] = $proposal['base_price'];
                    if (isset($proposal['impacts'][$cid])) { $value['attribute_price'] = $proposal['impacts'][$cid]; }
                }
                unset($value);
                Product::flushPriceCache();
                $cache->setValue(null, $values);
                foreach ($ids as $cid) {
                    $value = Product::getPriceStatic($pid, true, $cid ?: false, 6);
                    demand($value !== null && is_finite((float)$value), 'Pronostico visible no disponible');
                    $proposed[$cid] = $value;
                }
            }
            foreach ($ids as $cid) {
                $result[] = ['id'=>$pid, 'combination_id'=>$cid, 'actual'=>$actual[$cid], 'proposed'=>$proposed[$cid]];
            }
        }
        $output = ['host'=>TEST_HOST, 'context'=>'Visitante sin sesion, cantidad 1, moneda y pais predeterminados', 'prices'=>$result,
            'currency'=>['iso_code'=>Context::getContext()->currency->iso_code, 'precision'=>(int)Context::getContext()->currency->precision, 'round_mode'=>(int)Configuration::get('PS_PRICE_ROUND_MODE')]];
        if (!empty($request['stock_visibility'])) { $output['stock_visibility'] = stockVisibility($request['products']); }
        return $output;
    } finally {
        Product::flushPriceCache();
        $db->execute('ROLLBACK');
    }
}
