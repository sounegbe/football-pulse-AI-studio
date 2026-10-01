let selectedContentType = "youtube_script";
let generating = false;
const generateButton = document.querySelector(".generate-button");
const newsInput = document.querySelector("#football-news");
const resultBox = document.querySelector(".result-box");
const typeButtons = document.querySelectorAll(".type-button");
function showResult(message) { resultBox.textContent = message; }
typeButtons.forEach((button) => {
    button.addEventListener("click", () => {
        typeButtons.forEach((btn) => {
            btn.classList.remove("active");
            btn.setAttribute("aria-pressed", "false");
        });
        button.classList.add("active");
        button.setAttribute("aria-pressed", "true");
        selectedContentType = button.dataset.contentType;
    });
});
generateButton.addEventListener("click", async () => {
    if (generating) return;
    const news = newsInput.value.trim();
    if (!news || news.length > 2000) {
        showResult(!news ? "Please enter some football news first." : "Please limit football news to 2,000 characters.");
        newsInput.focus();
        return;
    }
    const contentType = selectedContentType;
    generating = true;
    generateButton.disabled = true;
    typeButtons.forEach((button) => { button.disabled = true; });
    generateButton.textContent = "Generating...";
    resultBox.setAttribute("aria-busy", "true");
    showResult("Sending your request...");
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 15000);
    try {
        const response = await fetch("/api/generate", {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ news, content_type: contentType }), signal: controller.signal,
        });
        if (!response.ok) throw new Error(response.status === 422
            ? "The request was rejected. Check your news and content type, then try again."
            : "The server could not complete the request. Please try again.");
        let data;
        try { data = await response.json(); }
        catch { throw new Error("The server returned an invalid response. Please try again."); }
        if (typeof data.content !== "string" || !data.content.trim() || data.content_type !== contentType || data.mode !== "stub")
            throw new Error("The server returned an unexpected response. Please try again.");
        showResult(`${data.content}\n\nContent type: ${data.content_type}\nMode: Test response (AI is not connected)`);
    } catch (error) {
        showResult(error.name === "AbortError" ? "The request timed out. Your news is still here; please try again."
            : error instanceof TypeError ? "Could not connect to the server. Your news is still here; please try again." : error.message);
    } finally {
        clearTimeout(timeout);
        generating = false;
        generateButton.disabled = false;
        typeButtons.forEach((button) => { button.disabled = false; });
        generateButton.textContent = "Generate Content";
        resultBox.setAttribute("aria-busy", "false");
    }
});
