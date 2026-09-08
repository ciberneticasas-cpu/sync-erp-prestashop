{*
* NOTICE OF LICENSE
*
* This source file is subject to the Academic Free License version 3.0
* that is bundled with this package in the file LICENSE.txt
* It is also available through the world-wide-web at this URL:
* https://opensource.org/licenses/AFL-3.0
*
* DISCLAIMER
*
* Do not edit or add to this file if you wish to upgrade this module to a newer
* versions in the future. If you wish to customize this module for your needs
* please refer to CustomizationPolicy.txt file inside our module for more information.
*
* @author Webkul IN
* @copyright Since 2010 Webkul
* @license https://opensource.org/licenses/AFL-3.0 Academic Free License version 3.0
*}
{* Keep the native wrapper, availability and minimum-quantity blocks for AJAX refresh. *}
{extends file='catalog/_partials/product-add-to-cart.tpl'}
{block name='product_quantity'}
      <div class="product-quantity clearfix">
        <div class="qtyW quantityWa widthQuantityWa">
          <input
            type="number"
            name="qty"
            id="quantity_wanted"
            inputmode="numeric"
            pattern="[0-9]*"
            {if $product.quantity_wanted}
              value="{$product.quantity_wanted}"
              min="{$product.minimal_quantity}"
            {else}
              value="1"
              min="1"
            {/if}
            class="input-group quantityWaQ"
            aria-label="{l s='Quantity' d='Shop.Theme.Actions'}"
          >
          <div class="quantityWa-nav">
            <button type="button" class="quantityWa-button quantityWa-up{if !$product.add_to_cart_url}-D{/if}">+</button><br>
            <button type="button" class="quantityWa-button quantityWa-down{if !$product.add_to_cart_url}-D{/if}">-</button>
          </div>
        </div>
        <div class="add">
          <button
            class="btn btn-primary add-to-cart"
            data-button-action="add-to-cart"
            type="submit"
            {if !$product.add_to_cart_url}
              disabled
            {else}
                disabled="disabled"
            {/if}
          >
            <i class="material-icons shopping_basket">&#xe8cb;</i>
            ÚSTELE AL CANASTO
          </button>
        </div>
        {*Waplicaciones Alejandro ardila hook h='displayProductActions' product=$product*}
      </div>
    {/block}
