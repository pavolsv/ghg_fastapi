
        // 從 URL 取得年度
        function getYearFromUrl() {
            const pathParts = window.location.pathname.split('/');
            return pathParts[pathParts.length - 1] || '2024';
        }

        const currentYear = getYearFromUrl();
        document.getElementById('currentYear').textContent = currentYear;

        let currentEditId = null;

        // 返回年度列表
        function goToList() {
            window.location.href = '/inventory_list';
        }

        // 載入邊界資料
        async function loadBoundaries() {
            try {
                const response = await fetch(`/inventory_list/boundary/${currentYear}/list`);
                const result = await response.json();
                
                if (result.success) {
                    const boundaryList = document.getElementById('boundaryList');
                    boundaryList.innerHTML = '';
                    
                    result.data.forEach(boundary => {
                        addBoundaryToList(boundary.boundary_name, boundary.address, boundary.boundary_id, false);
                    });
                    
                    updateBoundaryNumbers();
                    updateEmptyState();
                    updateBoundaryCount();
                }
            } catch (error) {
                console.error('載入邊界資料失敗:', error);
            }
        }

        // 新增邊界
        async function addBoundary() {
            const name = document.getElementById('boundaryName').value.trim();
            const address = document.getElementById('boundaryAddress').value.trim();
            const imageInput = document.getElementById('boundaryImage');
            const imageFile = imageInput.files[0];

            if (!name) {
                alert('請輸入邊界名稱');
                document.getElementById('boundaryName').focus();
                return;
            }

            if (!address) {
                alert('請輸入地址');
                document.getElementById('boundaryAddress').focus();
                return;
            }

            const addBtn = document.getElementById('addBtn');
            const originalText = addBtn.textContent;
            addBtn.innerHTML = '<span class="loading"></span> 新增中...';
            addBtn.disabled = true;

            try {
                const response = await fetch(`/inventory_list/boundary/${currentYear}/add`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        boundary_name: name,
                        address: address
                    })
                });

                const result = await response.json();

                if (result.success) {
                    addBoundaryToList(name, address, result.boundary_id, true);
                    if (imageFile) {
                        await readBoundaryImageFile(result.boundary_id, imageFile);
                    }
                    document.getElementById('boundaryName').value = '';
                    document.getElementById('boundaryAddress').value = '';
                    imageInput.value = '';
                    setBoundaryImagePreview(null, 'boundaryImagePreview');
                } else {
                    alert(result.message || '新增失敗');
                }
            } catch (error) {
                console.error('Error:', error);
                alert('系統錯誤，請稍後再試');
            } finally {
                addBtn.textContent = originalText;
                addBtn.disabled = false;
            }
        }

        // 將邊界加入列表
        function addBoundaryToList(name, address, boundaryId, showAlert = false) {
            const boundaryList = document.getElementById('boundaryList');
            
            const newItem = document.createElement('div');
            newItem.className = 'boundary-item';
            newItem.setAttribute('data-id', boundaryId);
            newItem.innerHTML = `
                <div class="boundary-number">${getNextNumber()}</div>
                <div class="boundary-info">
                    <div class="boundary-name">${escapeHtml(name)}</div>
                    <div class="boundary-address">${escapeHtml(address)}</div>
                </div>
                <div class="boundary-actions">
                    <button type="button" class="btn-icon" onclick="editBoundary(this)" title="編輯">✎</button>
                    <button type="button" class="btn-icon preview-button" onclick="previewBoundaryImage(this)" title="預覽組織邊界圖" style="display:none;">🖼️</button>
                    <button type="button" class="btn-icon" onclick="deleteBoundary(this)" title="刪除">🗑️</button>
                </div>
            `;

            boundaryList.appendChild(newItem);
            renderBoundaryPreviewButton(newItem, boundaryId);
            
            updateBoundaryNumbers();
            updateEmptyState();
            updateBoundaryCount();
        }

        function getNextNumber() {
            const items = document.querySelectorAll('.boundary-item');
            return items.length + 1;
        }

        function updateBoundaryNumbers() {
            const items = document.querySelectorAll('.boundary-item');
            items.forEach((item, index) => {
                const numberDiv = item.querySelector('.boundary-number');
                if (numberDiv) {
                    numberDiv.textContent = index + 1;
                }
            });
        }

        function editBoundary(button) {
            const boundaryItem = button.closest('.boundary-item');
            if (!boundaryItem) {
                console.warn('找不到要編輯的邊界項目');
                return;
            }

            currentEditId = boundaryItem.getAttribute('data-id');
            if (!currentEditId) {
                console.warn('無效的邊界 ID');
                return;
            }

            const nameElem = boundaryItem.querySelector('.boundary-name');
            const addressElem = boundaryItem.querySelector('.boundary-address');
            const name = nameElem ? nameElem.textContent : '';
            const address = addressElem ? addressElem.textContent : '';

            document.getElementById('editName').value = name;
            document.getElementById('editAddress').value = address;
            document.getElementById('editBoundaryImage').value = '';
            setBoundaryImagePreview(null, 'editBoundaryImagePreview');

            document.getElementById('editModal').classList.add('active');
        }

        function closeEditModal() {
            document.getElementById('editModal').classList.remove('active');
            currentEditId = null;
            document.getElementById('editName').value = '';
            document.getElementById('editAddress').value = '';
        }

        async function saveEdit() {
            const name = document.getElementById('editName').value.trim();
            const address = document.getElementById('editAddress').value.trim();

            if (!name || !address) {
                alert('請填寫完整資訊');
                return;
            }

            const saveBtn = document.querySelector('#editModal .btn-primary');
            const originalText = saveBtn.textContent;
            saveBtn.innerHTML = '<span class="loading"></span> 儲存中...';
            saveBtn.disabled = true;

            try {
                const response = await fetch(`/inventory_list/boundary/${currentYear}/edit/${currentEditId}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        boundary_name: name,
                        address: address
                    })
                });

                const result = await response.json();

                if (result.success) {
                    const boundaryItem = document.querySelector(`.boundary-item[data-id="${currentEditId}"]`);
                    if (boundaryItem) {
                        boundaryItem.querySelector('.boundary-name').textContent = name;
                        boundaryItem.querySelector('.boundary-address').textContent = address;
                    }
                    const editImageInput = document.getElementById('editBoundaryImage');
                    const editImageFile = editImageInput.files[0];
                    if (editImageFile) {
                        await readBoundaryImageFile(currentEditId, editImageFile);
                    }
                    closeEditModal();
                    alert('編輯成功！');
                } else {
                    alert(result.message || '編輯失敗');
                }
            } catch (error) {
                console.error('Error:', error);
                alert('系統錯誤，請稍後再試');
            } finally {
                saveBtn.textContent = originalText;
                saveBtn.disabled = false;
            }
        }

        async function deleteBoundary(button) {
            if (!confirm('確定要刪除此組織邊界嗎？')) return;

            const boundaryItem = button.closest('.boundary-item');
            const boundaryId = boundaryItem.getAttribute('data-id');

            button.disabled = true;
            button.textContent = '⋯';

            try {
                const response = await fetch(`/inventory_list/boundary/${currentYear}/delete/${boundaryId}`, {
                    method: 'DELETE'
                });

                const result = await response.json();

                if (result.success) {
                    boundaryItem.remove();
                    updateBoundaryNumbers();
                    updateEmptyState();
                    updateBoundaryCount();
                } else {
                    alert(result.message || '刪除失敗');
                    button.disabled = false;
                    button.textContent = '🗑️';
                }
            } catch (error) {
                console.error('Error:', error);
                alert('系統錯誤，請稍後再試');
                button.disabled = false;
                button.textContent = '🗑️';
            }
        }

        function updateEmptyState() {
            const items = document.querySelectorAll('.boundary-item');
            const emptyState = document.getElementById('emptyState');
            emptyState.style.display = items.length === 0 ? 'block' : 'none';
        }

        function updateBoundaryCount() {
            const items = document.querySelectorAll('.boundary-item');
            document.getElementById('boundaryCount').textContent = items.length + ' 筆';
        }

        function focusOnForm() {
            document.getElementById('boundaryName').focus();
        }

        function getStoredBoundaryImages() {
            try {
                const saved = localStorage.getItem('boundaryImageMap');
                return saved ? JSON.parse(saved) : {};
            } catch (error) {
                console.warn('讀取邊界圖片快取失敗', error);
                return {};
            }
        }

        function saveStoredBoundaryImages(map) {
            try {
                localStorage.setItem('boundaryImageMap', JSON.stringify(map));
            } catch (error) {
                console.warn('儲存邊界圖片快取失敗', error);
            }
        }

        const boundaryImageMap = getStoredBoundaryImages();

        function renderBoundaryPreviewButton(boundaryItem, boundaryId) {
            const previewButton = boundaryItem.querySelector('.preview-button');
            const hasImage = Boolean(boundaryImageMap[boundaryId]);
            if (previewButton) {
                previewButton.style.display = hasImage ? 'inline-flex' : 'none';
            }
        }

        function previewBoundaryImage(button) {
            const boundaryItem = button.closest('.boundary-item');
            if (!boundaryItem) {
                console.warn('找不到要預覽的邊界項目');
                openPreviewModal(null);
                return;
            }
            const boundaryId = boundaryItem.getAttribute('data-id');
            const imageData = boundaryImageMap[boundaryId];
            openPreviewModal(imageData);
        }

        function openPreviewModal(imageData) {
            const modal = document.getElementById('previewModal');
            const imageElement = document.getElementById('previewImage');
            const noImageElement = document.getElementById('previewNoImage');

            if (imageData) {
                imageElement.src = imageData;
                imageElement.style.display = 'block';
                noImageElement.style.display = 'none';
            } else {
                imageElement.style.display = 'none';
                noImageElement.style.display = 'block';
            }
            modal.classList.add('active');
        }

        function closePreviewModal() {
            document.getElementById('previewModal').classList.remove('active');
        }

        function setBoundaryImagePreview(file, previewId) {
            const previewContainer = document.getElementById(previewId);
            const nameLabel = document.getElementById(previewId + 'Name');
            if (!file) {
                previewContainer.style.display = 'none';
                nameLabel.textContent = '';
                return;
            }
            previewContainer.style.display = 'flex';
            nameLabel.textContent = file.name;
        }

        function saveBoundaryImageData(boundaryId, dataUrl) {
            boundaryImageMap[boundaryId] = dataUrl;
            saveStoredBoundaryImages(boundaryImageMap);
        }

        async function readBoundaryImageFile(boundaryId, file) {
            if (!file) return;
            const reader = new FileReader();
            reader.onload = function (event) {
                saveBoundaryImageData(boundaryId, event.target.result);
                const boundaryItem = document.querySelector(`.boundary-item[data-id="${boundaryId}"]`);
                if (boundaryItem) {
                    renderBoundaryPreviewButton(boundaryItem, boundaryId);
                }
            };
            reader.readAsDataURL(file);
        }

        function nextStep() {
            const boundaryCount = document.querySelectorAll('.boundary-item').length;
            if (boundaryCount === 0) {
                alert('請至少設定一個組織邊界');
                return;
            }
            window.location.href = `/inventory_list/emission/${currentYear}`;
        }

        function escapeHtml(unsafe) {
            return unsafe
                .replace(/&/g, "&amp;")
                .replace(/</g, "&lt;")
                .replace(/>/g, "&gt;")
                .replace(/"/g, "&quot;")
                .replace(/'/g, "&#039;");
        }

        // 初始化
        document.addEventListener('DOMContentLoaded', loadBoundaries);

        // 點擊模態框背景關閉
        document.getElementById('editModal').addEventListener('click', function(e) {
            if (e.target === this) closeEditModal();
        });

        // 鍵盤ESC關閉
        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape') closeEditModal();
        });
    