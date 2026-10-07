(function () {
  "use strict";

  const fields = [
    ["id_image", "image-preview"],
    ["id_image2", "image2-preview"],
    ["id_image3", "image3-preview"],
  ];

  function setupPreview(inputId, previewId) {
    const input = document.getElementById(inputId);
    const preview = document.getElementById(previewId);
    if (!input || !preview) return;

    const emptyMessage = preview.parentElement.querySelector(".image-preview-empty");
    let selectedUrl = null;

    input.addEventListener("change", function () {
      const file = input.files && input.files[0];
      if (!file) return;

      if (selectedUrl) URL.revokeObjectURL(selectedUrl);
      selectedUrl = URL.createObjectURL(file);
      preview.src = selectedUrl;
      preview.style.display = "";
      if (emptyMessage) emptyMessage.style.display = "none";
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    fields.forEach(function (field) {
      setupPreview(field[0], field[1]);
    });
  });
})();
