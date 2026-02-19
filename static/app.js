async function generateImage() {
    const input = document.getElementById("imageInput");
    const file = input.files[0];

    if (!file) {
        alert("Please upload an image.");
        return;
    }

    const formData = new FormData();
    formData.append("image", file);

    document.getElementById("preview").innerHTML = "Generating...";

    const response = await fetch("/api/generate", {
        method: "POST",
        body: formData
    });

    const data = await response.json();

    if (data.image_url) {
        document.getElementById("preview").innerHTML =
            `<img src="${data.image_url}"><br><a href="${data.image_url}" download>Download</a>`;
    } else {
        document.getElementById("preview").innerHTML = "Error generating image.";
    }
}
