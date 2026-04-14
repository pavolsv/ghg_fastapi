const billModal = document.getElementById('billModal');
const editBillModal = document.getElementById('editBillModal');
const editBillForm = document.getElementById('editBillForm');
const monthSortHeader = document.getElementById('monthSortHeader');
const monthSortIcon = document.getElementById('monthSortIcon');
const billsTableBody = document.getElementById('billsTableBody');

let monthAsc = false;

function openModal() {
    const billModal = document.getElementById('billModal');
    if (billModal) billModal.style.display = 'flex';
}

function closeModal() {
    const billModal = document.getElementById('billModal');
    if (billModal) billModal.style.display = 'none';
}

function onOverlayClick(event) {
    const billModal = document.getElementById('billModal');
    if (billModal && event.target === billModal) {
        closeModal();
    }
}

function openEditModal(buttonElement) {
    const billId = buttonElement.dataset.id;
    editBillForm.action = `/documents/update/${billId}`;

    // Fuel bill fields (conditionally rendered)
    const editFuelDate = document.getElementById('edit_fuel_date');
    const editFuelType = document.getElementById('edit_fuel_type');

    if (editFuelDate) {
        // Fuel bill mode: use period_start as the date
        editFuelDate.value = buttonElement.dataset.periodStart || '';
    } else {
        document.getElementById('edit_bill_month').value = buttonElement.dataset.billMonth || '';
        document.getElementById('edit_period_start').value = buttonElement.dataset.periodStart || '';
        document.getElementById('edit_period_end').value = buttonElement.dataset.periodEnd || '';
    }

    document.getElementById('edit_usage_amount').value = buttonElement.dataset.usageAmount || '';
    document.getElementById('edit_unit').value = buttonElement.dataset.unit || '';
    document.getElementById('edit_note').value = buttonElement.dataset.note || '';

    if (editFuelType) {
        editFuelType.value = buttonElement.dataset.fuelType || '';
    }

    editBillModal.style.display = 'flex';
}

function closeEditModal() {
    editBillModal.style.display = 'none';
}

function onEditOverlayClick(event) {
    if (event.target === editBillModal) {
        closeEditModal();
    }
}

function updateEditedRow(bill) {
    const row = billsTableBody.querySelector(`tr[data-bill-id="${bill.id}"]`);
    if (!row) {
        return;
    }

    row.dataset.month = bill.bill_month;
    row.querySelector('.col-bill-month').textContent = bill.bill_month;
    row.querySelector('.col-period').textContent = `${bill.period_start} ~ ${bill.period_end}`;
    row.querySelector('.col-usage-amount').textContent = `${bill.usage_amount}`;
    row.querySelector('.col-unit').textContent = bill.unit;
    row.querySelector('.col-note').textContent = bill.note || '-';

    const fuelTypeCell = row.querySelector('.col-fuel-type');
    if (fuelTypeCell) {
        fuelTypeCell.textContent = bill.fuel_type || '-';
    }

    const editButton = row.querySelector('.btn-edit');
    if (editButton) {
        editButton.dataset.billMonth = bill.bill_month;
        editButton.dataset.periodStart = bill.period_start;
        editButton.dataset.periodEnd = bill.period_end;
        editButton.dataset.usageAmount = `${bill.usage_amount}`;
        editButton.dataset.unit = bill.unit;
        editButton.dataset.note = bill.note || '';
        editButton.dataset.fuelType = bill.fuel_type || '';
    }
}

async function submitEditBill(event) {
    event.preventDefault();

    const formData = new FormData(editBillForm);
    const response = await fetch(editBillForm.action, {
        method: 'POST',
        headers: {
            'X-Requested-With': 'XMLHttpRequest',
        },
        body: formData,
    });

    if (!response.ok) {
        alert('更新失敗，請稍後再試。');
        return;
    }

    const result = await response.json();
    if (!result.success || !result.bill) {
        alert(result.message || '更新失敗，請稍後再試。');
        return;
    }

    updateEditedRow(result.bill);
    closeEditModal();
}

function sortByMonth() {
    const rows = Array.from(billsTableBody.querySelectorAll('tr'));
    rows.sort((a, b) => {
        const monthA = a.dataset.month || '';
        const monthB = b.dataset.month || '';
        return monthAsc ? monthA.localeCompare(monthB) : monthB.localeCompare(monthA);
    });
    rows.forEach((row) => billsTableBody.appendChild(row));
    monthSortIcon.textContent = monthAsc ? '↑' : '↓';
    monthAsc = !monthAsc;
}

monthSortHeader.addEventListener('click', sortByMonth);
editBillForm.addEventListener('submit', submitEditBill);
