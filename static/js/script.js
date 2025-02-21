document.addEventListener('DOMContentLoaded', function() {
  console.log("Script loaded.");
  const copyButton = document.getElementById('copy-button');
  if (copyButton) {
    copyButton.addEventListener('click', function() {
      const userKeyElement = document.getElementById('user-key');
      if (!userKeyElement) {
        console.error("Element with id 'user-key' not found.");
        return;
      }
      // Use textContent and trim whitespace
      const userKey = userKeyElement.textContent.trim();
      console.log("Copying widget key:", userKey);
      navigator.clipboard.writeText(userKey)
        .then(() => {
          alert('Widget key copied!');
        })
        .catch((err) => {
          console.error("Copy failed:", err);
          alert('Failed to copy: ' + err);
        });
    });
  } else {
    console.error("Copy button not found.");
  }
});
