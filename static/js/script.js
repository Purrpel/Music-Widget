document.addEventListener('DOMContentLoaded', function() {
  const copyButton = document.getElementById('copy-button');
  if (copyButton) {
    copyButton.addEventListener('click', function() {
      const userKey = document.getElementById('user-key').innerText;
      navigator.clipboard.writeText(userKey)
        .then(() => {
          alert('Widget key copied!');
        })
        .catch((err) => {
          alert('Failed to copy: ' + err);
        });
    });
  }
});
