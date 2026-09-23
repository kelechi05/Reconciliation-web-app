(function () {
    var messages = [
        "Reading Excel files...",
        "Matching transactions...",
        "Generating report...",
        "Please wait..."
    ];

    function showProcessingOverlay() {
        var overlay = document.querySelector("[data-processing-overlay]");
        var statusText = document.querySelector("[data-processing-status]");
        var matchButton = document.querySelector("[data-match-submit]");

        if (!overlay || !statusText) {
            return;
        }

        var messageIndex = 0;
        statusText.textContent = messages[messageIndex];
        overlay.hidden = false;
        overlay.setAttribute("aria-hidden", "false");

        if (matchButton) {
            matchButton.disabled = true;
            matchButton.textContent = "Processing...";
        }

        window.setInterval(function () {
            messageIndex = (messageIndex + 1) % messages.length;
            statusText.textContent = messages[messageIndex];
        }, 1200);
    }

    document.addEventListener("DOMContentLoaded", function () {
        var uploadForm = document.querySelector("[data-match-form]");

        if (!uploadForm) {
            return;
        }

        uploadForm.addEventListener("submit", showProcessingOverlay);
    });
})();
