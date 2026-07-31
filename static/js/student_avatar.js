(function (window, document) {
    'use strict';

    function modalInstance(element) {
        if (window.bootstrap && window.bootstrap.Modal) {
            return window.bootstrap.Modal.getOrCreateInstance(element);
        }
        return {
            show: function () { window.jQuery(element).modal('show'); },
            hide: function () { window.jQuery(element).modal('hide'); }
        };
    }

    function requestJson(url, options) {
        var requestOptions = Object.assign({}, options || {});
        var method = String(requestOptions.method || 'GET').toUpperCase();
        if (method !== 'GET' && method !== 'HEAD' && method !== 'OPTIONS') {
            var csrfMeta = document.querySelector('meta[name="csrf-token"]');
            var csrfToken = csrfMeta ? csrfMeta.content : '';
            var requestHeaders = new Headers(requestOptions.headers || {});
            if (csrfToken) {
                requestHeaders.set('X-CSRFToken', csrfToken);
            }
            requestOptions.headers = requestHeaders;
        }
        var requestOptions = Object.assign({}, options || {});
        var method = String(requestOptions.method || 'GET').toUpperCase();
        if (['GET', 'HEAD', 'OPTIONS'].indexOf(method) === -1) {
            var csrfMeta = document.querySelector('meta[name="csrf-token"]');
            var csrfToken = csrfMeta ? csrfMeta.getAttribute('content') : '';
            if (csrfToken) {
                var requestHeaders = new window.Headers(requestOptions.headers || {});
                requestHeaders.set('X-CSRFToken', csrfToken);
                requestOptions.headers = requestHeaders;
            }
        }

        return window.fetch(url, requestOptions).then(function (response) {
            return response.json().catch(function () { return {}; }).then(function (data) {
                if (!response.ok) {
                    var error = new Error(
                        data.error && data.error.message ? data.error.message : '头像操作失败'
                    );
                    error.status = response.status;
                    error.code = data.error && data.error.code ? data.error.code : null;
                    throw error;
                }
                return data;
            });
        });
    }

    function cacheBustedUrl(url, image) {
        if (!url) {
            return null;
        }
        var separator = url.indexOf('?') === -1 ? '?' : '&';
        var version = image && (image.id || image.updated_at);
        return url + separator + 'v=' + encodeURIComponent(
            String(version || 'avatar') + '-' + Date.now()
        );
    }

    function createLibraryCard(item, onSelect) {
        var column = document.createElement('div');
        column.className = 'col-6 col-md-4 col-lg-3 mb-3';

        var card = document.createElement('div');
        card.className = 'card h-100 shadow-sm';

        var image = document.createElement('img');
        image.className = 'card-img-top';
        image.src = item.avatar_url;
        image.alt = item.original_filename || '学生图像';
        image.style.height = '166px';
        image.style.objectFit = 'cover';

        var body = document.createElement('div');
        body.className = 'card-body d-flex flex-column p-2';

        var title = document.createElement('div');
        title.className = 'small font-weight-bold text-truncate mb-1';
        title.textContent = item.student_name || item.parsed_name || '未命名图像';
        title.title = title.textContent;

        var meta = document.createElement('div');
        meta.className = 'small text-muted text-truncate mb-2';
        meta.textContent = item.student_no || item.parsed_student_no || item.original_filename || '--';
        meta.title = meta.textContent;

        var button = document.createElement('button');
        button.type = 'button';
        button.className = 'btn btn-sm btn-outline-primary mt-auto avatar-library-select';
        button.textContent = '选择此图像';
        button.addEventListener('click', function () { onSelect(item, button); });

        body.appendChild(title);
        body.appendChild(meta);
        body.appendChild(button);
        card.appendChild(image);
        card.appendChild(body);
        column.appendChild(card);
        return column;
    }

    window.StudentAvatar = {
        mount: function (options) {
            var studentId = Number(options.studentId);
            var avatar = document.querySelector(options.avatarSelector);
            var avatarDefault = document.querySelector(options.defaultSelector);
            var nameElement = document.querySelector(options.nameSelector);
            var modalElement = document.querySelector('.avatar-library-modal');
            var grid = document.querySelector('.avatar-library-grid');
            var alertBox = document.querySelector('.avatar-library-alert');
            var fileInput = document.querySelector('.avatar-local-upload');
            var libraryButtons = document.querySelectorAll('.avatar-library-open');
            var uploadButtons = document.querySelectorAll('.avatar-local-upload-button');
            var modal = modalElement ? modalInstance(modalElement) : null;

            function showMessage(message, type) {
                if (!alertBox) {
                    return;
                }
                alertBox.textContent = message || '';
                alertBox.className = 'avatar-library-alert' + (
                    message ? ' alert alert-' + (type || 'danger') : ''
                );
            }

            function displayName(name) {
                var value = name || (nameElement ? nameElement.textContent : '');
                value = String(value || '').trim();
                return value && value !== '--' ? value.charAt(0) : '--';
            }

            function renderPortrait(avatarUrl, name, image) {
                if (avatarUrl) {
                    avatar.src = image ? cacheBustedUrl(avatarUrl, image) : avatarUrl;
                    avatar.classList.remove('d-none');
                    avatarDefault.classList.add('d-none');
                    return;
                }
                avatar.removeAttribute('src');
                avatar.classList.add('d-none');
                avatarDefault.textContent = displayName(name);
                avatarDefault.classList.remove('d-none');
            }

            function bindImage(item, button, confirmReplace) {
                button.disabled = true;
                showMessage('', 'danger');
                return requestJson('/api/student-images/' + item.id + '/bind', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        student_id: studentId,
                        confirm_replace: Boolean(confirmReplace)
                    })
                }).then(function (image) {
                    renderPortrait(image.avatar_url, null, image);
                    modal.hide();
                }).catch(function (error) {
                    if (
                        error.status === 409 && error.code === 'binding_conflict' &&
                        !confirmReplace &&
                        window.confirm(error.message + '\n确认后将替换现有头像，是否继续？')
                    ) {
                        return bindImage(item, button, true);
                    }
                    showMessage(error.message, 'danger');
                }).finally(function () {
                    button.disabled = false;
                });
            }

            function loadLibrary() {
                grid.replaceChildren();
                var loading = document.createElement('div');
                loading.className = 'col-12 py-5 text-center text-muted';
                loading.textContent = '正在加载图像……';
                grid.appendChild(loading);
                showMessage('', 'danger');

                requestJson('/api/student-images?per_page=100').then(function (data) {
                    grid.replaceChildren();
                    var items = Array.isArray(data.items) ? data.items : [];
                    if (!items.length) {
                        loading.textContent = '当前班级图像库暂无图片。';
                        grid.appendChild(loading);
                        return;
                    }
                    items.forEach(function (item) {
                        grid.appendChild(createLibraryCard(item, bindImage));
                    });
                }).catch(function (error) {
                    grid.replaceChildren();
                    loading.textContent = '图像加载失败。';
                    grid.appendChild(loading);
                    showMessage(error.message, 'danger');
                });
            }

            function uploadLocalFile(file, confirmReplace) {
                var formData = new window.FormData();
                formData.append('file', file);
                if (confirmReplace) {
                    formData.append('confirm_replace', 'true');
                }
                uploadButtons.forEach(function (button) { button.disabled = true; });

                requestJson('/api/student/' + studentId + '/image', {
                    method: 'POST',
                    body: formData
                }).then(function (result) {
                    var image = result.image || result;
                    renderPortrait(image.avatar_url, null, image);
                }).catch(function (error) {
                    if (
                        error.status === 409 && error.code === 'binding_conflict' &&
                        !confirmReplace &&
                        window.confirm(error.message + '\n确认后将替换现有头像，是否继续？')
                    ) {
                        return uploadLocalFile(file, true);
                    }
                    window.alert(error.message);
                }).finally(function () {
                    fileInput.value = '';
                    uploadButtons.forEach(function (button) { button.disabled = false; });
                });
            }

            libraryButtons.forEach(function (button) {
                button.addEventListener('click', function () {
                    loadLibrary();
                    modal.show();
                });
            });
            uploadButtons.forEach(function (button) {
                button.addEventListener('click', function () { fileInput.click(); });
            });
            fileInput.addEventListener('change', function () {
                var file = fileInput.files && fileInput.files[0];
                if (file) {
                    uploadLocalFile(file, false);
                }
            });

            renderPortrait(null, null, null);
            return {render: renderPortrait};
        }
    };
})(window, document);
