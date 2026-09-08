<?php
/** Install the module template override only on the authorized test clone. */
declare(strict_types=1);
define('MERCABOY_LIBRARY_ONLY', true);
require __DIR__ . '/bridge.php';
try {
    demand(trim(file_get_contents('/sys/class/dmi/id/product_uuid')) === 'f5fdbff6-4272-4082-b459-91c7dcf97d56', 'Solo clon 311');
    $settings = json_decode(file_get_contents(__DIR__ . '/settings.json'), true, 512, JSON_THROW_ON_ERROR);
    $parameters = localParameters($settings);
    $db = connection($settings, $parameters);
    $db->close();
    $relative = 'wkcustomhyperlocal/views/templates/hook/product-add-to-cart.tpl';
    $source = file_get_contents(__DIR__ . '/theme_overrides/' . $relative);
    $target = '/var/www/html/themes/classic/modules/' . $relative;
    demand(!file_exists($target) || file_get_contents($target) === $source, 'Ya existe otra personalizacion: revisar antes de sustituir');
    $apply = in_array('--apply', $argv, true);
    if ($apply) {
        boot();
        if (!is_dir(dirname($target))) { mkdir(dirname($target), 0755, true); }
        demand(file_put_contents($target, $source) === strlen($source), 'No se pudo instalar la plantilla');
        chmod($target, 0644);
        Tools::clearSmartyCache();
        Cache::clean('*');
    }
    echo json_encode(['applied' => $apply, 'host' => TEST_HOST, 'template' => $target], JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES) . "\n";
} catch (Throwable $error) {
    fwrite(STDERR, $error->getMessage() . "\n");
    exit(1);
}
