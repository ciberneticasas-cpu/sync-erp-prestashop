<?php
/** Read-only stock visibility, using the installed module's category expansion and stock logic. */
function stockModuleRead($module, string $method, array $arguments = []) {
    $reader = new ReflectionMethod($module, $method);
    $reader->setAccessible(true);
    return $reader->invokeArgs($module, $arguments);
}
function stockVisibility(array $products): array {
    $enabled = Module::isEnabled('stockthresholdhide') && (bool)Configuration::get('STOCKTHRESHOLDHIDE_ENABLED');
    $module = $enabled ? Module::getInstanceByName('stockthresholdhide') : null;
    demand(!$enabled || $module, 'Modulo de stock no disponible');
    $mode = (string)Configuration::get('STOCKTHRESHOLDHIDE_CATEGORY_MODE');
    $block = $enabled && (bool)Configuration::get('STOCKTHRESHOLDHIDE_BLOCK_PRODUCT_PAGE');
    $rules = [];
    $categories = [];
    if ($enabled) {
        // Expand each category rule once, instead of repeating it for every product.
        if ($mode === 'rules') {
            foreach (stockModuleRead($module, 'getCategoryRules') as $rule) {
                $rules[] = ['categories'=>array_fill_keys(stockModuleRead($module, 'getEffectiveRuleCategoryIds', [$rule]), true),
                            'minimum'=>(int)$rule['min_qty'], 'label'=>$rule['id_category'].':'.$rule['min_qty']];
            }
        } else {
            $rules[] = ['categories'=>$mode === 'selected' ? array_fill_keys(stockModuleRead($module, 'getEffectiveSelectedCategoryIds'), true) : null,
                        'minimum'=>(int)Configuration::get('STOCKTHRESHOLDHIDE_MIN_QTY'), 'label'=>$mode];
        }
        $rows = Db::getInstance()->executeS('SELECT id_product, id_category FROM `'._DB_PREFIX_.'category_product`');
        demand(is_array($rows), 'No se pudieron leer categorias para stock');
        foreach ($rows as $row) { $categories[(int)$row['id_product']][(int)$row['id_category']] = true; }
    }
    $result = [];
    foreach ($products as $product) {
        $id = (int)$product['id']; $minimum = 0; $matched = [];
        foreach ($rules as $rule) {
            if ($rule['categories'] === null || array_intersect_key($categories[$id] ?? [], $rule['categories'])) {
                $minimum = max($minimum, $rule['minimum']); $matched[] = $rule['label'];
            }
        }
        $quantity = (int)StockAvailable::getQuantityAvailableByProduct($id, null, 1);
        if ($enabled && $quantity <= 0) { $quantity = (int)stockModuleRead($module, 'getProductTotalQuantityFromDatabase', [$id]); }
        $hidden = $enabled && $minimum > 0 && $quantity < $minimum;
        $result[(string)$id] = ['quantity'=>$quantity, 'minimum'=>$minimum, 'hidden'=>$hidden,
            'page_blocked'=>$hidden && $block, 'rules'=>implode(';', $matched),
            'reason'=>!$enabled ? 'MODULO_DESACTIVADO' : ($minimum <= 0 ? 'SIN_REGLA_APLICABLE' : ($hidden ? 'INVENTARIO_BAJO' : 'CUMPLE_MINIMO'))];
    }
    return $result;
}
