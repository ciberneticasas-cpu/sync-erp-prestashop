<?php
/** Restore native selector hooks in the customized Classic theme on clone 311. */
declare(strict_types=1);
define('MERCABOY_LIBRARY_ONLY', true);
require __DIR__ . '/bridge.php';

try {
    $request = json_decode(file_get_contents(__DIR__ . '/settings.json'), true, 512, JSON_THROW_ON_ERROR);
    demand(trim(file_get_contents('/sys/class/dmi/id/product_uuid')) === 'f5fdbff6-4272-4082-b459-91c7dcf97d56', 'Solo clon 311');
    $parameters = localParameters($request);
    $db = connection($request, $parameters);
    $db->close();
    $root = '/var/www/html/themes/classic/templates/catalog/_partials/';
    $changes = [
        'product-variants.tpl' => [
            '<div class="product-variant js-product-variant">' => '<div class="{if !empty($mercaboy_miniature)}product-variant js-product-variant{else}product-variants js-product-variants{/if}">',
        ],
        'miniatures/product.tpl' => [
            'class="product-actions js-product-actions"' => 'class="product-list-actions js-product-list-actions"',
            "{include file='catalog/_partials/product-variants.tpl' groups=\$groups}" => "{include file='catalog/_partials/product-variants.tpl' groups=\$groups mercaboy_miniature=true}",
            "{include file='catalog/_partials/product-variants.tpl' }" => "{include file='catalog/_partials/product-variants.tpl' mercaboy_miniature=true}",
        ],
    ];
    // Isolate list-card controls from the native product-page refresh selectors.
    $changes['miniatures/product.tpl']["{include file='catalog/_partials/product-add-to-cart.tpl'}"] = "{include file='catalog/_partials/product-add-to-cart.tpl' mercaboy_miniature=true}";
    $changes['miniatures/product.tpl']['id="add-to-cart-or-refresh"'] = 'id="list-add-to-cart-{$product.id}"';
    $changes['miniatures/product.tpl']['id="product_page_product_id"'] = 'id="list-product-id-{$product.id}"';
    $changes['miniatures/product.tpl']['id="product_customization_id"'] = 'id="list-customization-id-{$product.id}"';
    $changes['product-add-to-cart.tpl'] = [
        'class="product-add-to-cart js-product-add-to-cart"' => 'class="{if !empty($mercaboy_miniature)}product-list-add-to-cart{else}product-add-to-cart js-product-add-to-cart{/if}"',
        'id="quantity_wanted"' => 'id="{if !empty($mercaboy_miniature)}list-quantity-{$product.id}{else}quantity_wanted{/if}"',
        'id="product-availability" class="js-product-availability"' => 'id="{if !empty($mercaboy_miniature)}list-availability-{$product.id}{else}product-availability{/if}" class="{if !empty($mercaboy_miniature)}list-product-availability{else}js-product-availability{/if}"',
        'class="product-minimal-quantity js-product-minimal-quantity"' => 'class="{if !empty($mercaboy_miniature)}list-minimal-quantity{else}product-minimal-quantity js-product-minimal-quantity{/if}"',
    ];
    $pending = [];
    foreach ($changes as $file => $replacements) {
        $original = file_get_contents($root . $file);
        $updated = $original;
        foreach ($replacements as $from => $to) {
            if (strpos($updated, $to) !== false) { continue; }
            demand(substr_count($updated, $from) === 1, 'Plantilla inesperada: ' . $file);
            $updated = str_replace($from, $to, $updated);
        }
        if ($original !== $updated) { $pending[$file] = [$original, $updated]; }
    }
    $apply = in_array('--apply', $argv, true);
    $backup = __DIR__ . '/reports/clon311/selector_tema_original_' . date('Ymd_His');
    if ($apply) {
        foreach ($pending as $file => [$original, $updated]) {
            $destination = $backup . '/' . $file;
            if (!is_dir(dirname($destination))) { mkdir(dirname($destination), 0755, true); }
            demand(!file_exists($destination), 'Ya existe copia original: ' . $file);
            demand(file_put_contents($destination, $original) === strlen($original), 'No se guardo copia original');
        }
        foreach ($pending as $file => [$original, $updated]) {
            demand(file_put_contents($root . $file, $updated) === strlen($updated), 'No se guardo plantilla');
        }
        boot();
        Tools::clearSmartyCache();
        Cache::clean('*');
        Configuration::updateValue('PS_COMBINATION_FEATURE_ACTIVE', 1);
        Configuration::updateValue('PS_DISP_UNAVAILABLE_ATTR', 1);
    }
    echo json_encode(['applied' => $apply, 'host' => TEST_HOST, 'files' => array_keys($pending),
        'original_templates' => $backup], JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES) . "\n";
} catch (Throwable $error) {
    fwrite(STDERR, $error->getMessage() . "\n");
    exit(1);
}
