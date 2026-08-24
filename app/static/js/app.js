console.log("Football Pulse JS loaded");

let selectedContentType = "youtube_script";

const generateButton = document.querySelector(".generate-button");

const newsInput = document.querySelector("#football-news");

const resultBox = document.querySelector(".result-box");

const typeButtons = document.querySelectorAll(".type-button");


typeButtons.forEach(function (button) {

    button.addEventListener("click", function () {

        typeButtons.forEach(function (btn) {
            btn.classList.remove("active");
        });

        button.classList.add("active");

        if (button.textContent.includes("News Article")) {
            selectedContentType = "news_article";
        } else if (button.textContent.includes("YouTube Script")) {
            selectedContentType = "youtube_script";
        } else if (button.textContent.includes("Short Video")) {
            selectedContentType = "short_video";
        } else if (button.textContent.includes("Social Post")) {
            selectedContentType = "social_post";
        }

        console.log("Selected content type:", selectedContentType);
    });

});

generateButton.addEventListener("click", async function () {

    const news = newsInput.value.trim();

    if (!news) {
        resultBox.innerHTML = "<p>Please enter some football news first.</p>";
        return;
    }

resultBox.innerHTML = `
    <p>${data.content}</p>
    <small>Content type: ${data.content_type}</small>
`;
    const response = await fetch("/api/generate", {

        method: "POST",

        headers: {
            "Content-Type": "application/json"
        },

        body: JSON.stringify({
            news: news,
            content_type: selectedContentType
        })

    });

    const data = await response.json();

    resultBox.innerHTML = `<p>${data.content}</p>`;

});