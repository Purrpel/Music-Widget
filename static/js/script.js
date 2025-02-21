document.addEventListener('DOMContentLoaded', function () {
  console.log("Script loaded.");

  const copyButton = document.getElementById('copy-button');
  const userKeyElement = document.getElementById('user-key');

  if (copyButton && userKeyElement) {
    copyButton.addEventListener('click', function () {
      const userKey = userKeyElement.innerText.trim(); // Use innerText to avoid unexpected HTML interference

      if (!userKey) {
        console.error("No widget key found.");
        return;
      }

      navigator.clipboard.writeText(userKey)
        .then(() => {
          alert('Widget key copied successfully!');
        })
        .catch((err) => {
          console.error("Copy failed:", err);
          alert('Failed to copy: ' + err);
        });
    });
  } else {
    console.error("Copy button or user key not found.");
  }
});
