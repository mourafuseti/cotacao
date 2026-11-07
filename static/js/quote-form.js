const itemsContainer = document.getElementById("items-container");
const addItemButton = document.getElementById("add-item");
const emptyItemTemplate = document.getElementById("empty-item-form");

if (itemsContainer && addItemButton && emptyItemTemplate) {
    const prefix = itemsContainer.dataset.formsetPrefix;
    const totalForms = document.getElementById(`id_${prefix}-TOTAL_FORMS`);
    const maxForms = Number(document.getElementById(`id_${prefix}-MAX_NUM_FORMS`).value);

    const appendItemRow = () => {
        const index = Number(totalForms.value);
        if (index >= maxForms) {
            addItemButton.disabled = true;
            return null;
        }
        const html = emptyItemTemplate.innerHTML.replaceAll("__prefix__", index);
        itemsContainer.insertAdjacentHTML("beforeend", html);
        totalForms.value = String(index + 1);
        addItemButton.disabled = index + 1 >= maxForms;
        return itemsContainer
            .querySelector(`[name="${prefix}-${index}-name"]`)
            .closest("[data-item-row]");
    };

    addItemButton.addEventListener("click", appendItemRow);

    const catalogPicker = document.getElementById("catalog-product-picker");
    const addCatalogProductButton = document.getElementById("add-catalog-product");
    if (catalogPicker && addCatalogProductButton) {
        addCatalogProductButton.addEventListener("click", () => {
            const option = catalogPicker.selectedOptions[0];
            if (!option || !option.value) {
                catalogPicker.focus();
                return;
            }

            let row = [...itemsContainer.querySelectorAll("[data-item-row]")].find((itemRow) => {
                const nameField = itemRow.querySelector('input[name$="-name"]');
                const deleteField = itemRow.querySelector('input[name$="-DELETE"]');
                return nameField && !itemRow.hidden && !deleteField?.checked && !nameField.value.trim();
            });
            if (!row) {
                row = appendItemRow();
            }
            if (!row) {
                return;
            }

            const nameField = row.querySelector('input[name$="-name"]');
            const productField = row.querySelector('input[name$="-product"]');
            const quantityField = row.querySelector('input[name$="-quantity"]');
            const unitField = row.querySelector('input[name$="-unit"]');
            const specificationsField = row.querySelector('input[name$="-specifications"]');
            const details = [];
            if (option.dataset.brand) details.push(`Marca: ${option.dataset.brand}`);
            if (option.dataset.partNumber) details.push(`PN: ${option.dataset.partNumber}`);

            nameField.value = option.dataset.name;
            nameField.dataset.catalogName = option.dataset.name;
            productField.value = option.value;
            if (quantityField && !quantityField.value) quantityField.value = "1";
            if (unitField && !unitField.value) unitField.value = "unidade";
            if (specificationsField && !specificationsField.value) {
                specificationsField.value = details.join(" · ").slice(0, 240);
            }
            catalogPicker.value = "";
        });
    }

    itemsContainer.addEventListener("change", (event) => {
        if (event.target.matches('input[type="checkbox"][name$="-DELETE"]')) {
            event.target.closest("[data-item-row]").hidden = event.target.checked;
        }
    });

    itemsContainer.addEventListener("input", (event) => {
        if (event.target.matches('input[name$="-name"]')) {
            const productField = event.target
                .closest("[data-item-row]")
                .querySelector('input[name$="-product"]');
            if (event.target.value !== event.target.dataset.catalogName) {
                productField.value = "";
                delete event.target.dataset.catalogName;
            }
        }
    });
}

const catalogSearch = document.getElementById("catalog-product-search");
const catalogSelect = document.getElementById("catalog-product-picker");
if (catalogSearch && catalogSelect) {
    catalogSearch.addEventListener("input", () => {
        const query = catalogSearch.value.trim().toLocaleLowerCase();
        [...catalogSelect.options].forEach((option, index) => {
            if (index > 0) {
                option.hidden = query !== "" && !option.text.toLocaleLowerCase().includes(query);
            }
        });
        if (catalogSelect.selectedOptions[0]?.hidden) {
            catalogSelect.value = "";
        }
    });
}
