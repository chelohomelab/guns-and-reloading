// Dollar amounts are private — blurred by default, tap to reveal.
(function () {
    const style = document.createElement('style');
    style.textContent = `
        .price-blur { filter: blur(6px); cursor: pointer; user-select: none; transition: filter .15s ease; display: inline-block; }
        .price-blur.price-revealed { filter: none; }
    `;
    document.head.appendChild(style);
})();

function blurPrice(amount, extraClass) {
    const val = `$${parseFloat(amount || 0).toFixed(2)}`;
    return `<span class="price-blur ${extraClass || ''}" title="Tap to reveal" onclick="event.stopPropagation(); this.classList.toggle('price-revealed')">${val}</span>`;
}
