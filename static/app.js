const fileInput = document.getElementById("file");
const dropzone = document.getElementById("dropzone");

const uploadStatus = document.getElementById("uploadStatus");
const uploadPreview = document.getElementById("uploadPreview");
const uploadPlaceholder = document.getElementById("uploadPlaceholder");

const genPreview = document.getElementById("genPreview");
const genPlaceholder = document.getElementById("genPlaceholder");

const generateBtn = document.getElementById("generateBtn");
const resetBtn = document.getElementById("resetBtn");

const downloadRow = document.getElementById("downloadRow");
const downloadPng = document.getElementById("downloadPng");
const downloadJpg = document.getElementById("downloadJpg");

let currentUploadId = null;

function setPill(text, type="muted"){
  uploadStatus.textContent = text;
  uploadStatus.className = "pill " + (type === "ok" ? "pill-ok" : type === "bad" ? "pill-bad" : "pill-muted");
}

function showUploadPreview(src){
  uploadPreview.src = src;
  uploadPreview.style.display = "block";
  uploadPlaceholder.style.display = "none";
}

function showGenPreview(src){
  genPreview.src = src;
  genPreview.style.display = "block";
  genPlaceholder.style.display = "none";
}

function clearAll(){
  currentUploadId = null;
  fileInput.value = "";
  uploadPreview.src = "";
  uploadPreview.style.display = "none";
  uploadPlaceholder.style.display = "flex";

  genPreview.src = "";
  genPreview.style.display = "none";
  genPlaceholder.style.display = "flex";

  downloadRow.style.display = "none";
  downloadPng.href = "#";
  downloadJpg.href = "#";

  generateBtn.disabled = true;
  resetBtn.disabled = true;

  setPill("No file selected", "muted");
}

async function uploadFile(file){
  const fd = new FormData();
  fd.append("file", file);

  setPill("Uploading...", "muted");
  generateBtn.disabled = true;
  resetBtn.disabled = false;

  // show local preview instantly
  const localUrl = URL.createObjectURL(file);
  showUploadPreview(localUrl);

  const res = await fetch("/api/upload", { method:"POST", body: fd });
  const data = await res.json();

  if(!data.ok){
    setPill("Upload failed ❌ " + (data.error || ""), "bad");
    currentUploadId = null;
    generateBtn.disabled = true;
    return;
  }

  currentUploadId = data.upload_id;
  setPill("Uploaded ✅", "ok");
  generateBtn.disabled = false;
  resetBtn.disabled = false;
}

fileInput.addEventListener("change", (e)=>{
  const file = e.target.files && e.target.files[0];
  if(!file) return;
  uploadFile(file).catch(err=>{
    setPill("Upload error ❌", "bad");
    console.error(err);
  });
});

// drag & drop UX
["dragenter","dragover"].forEach(ev=>{
  dropzone.addEventListener(ev, (e)=>{
    e.preventDefault();
    e.stopPropagation();
    dropzone.classList.add("dragover");
  });
});
["dragleave","drop"].forEach(ev=>{
  dropzone.addEventListener(ev, (e)=>{
    e.preventDefault();
    e.stopPropagation();
    dropzone.classList.remove("dragover");
  });
});

dropzone.addEventListener("drop", (e)=>{
  const file = e.dataTransfer.files && e.dataTransfer.files[0];
  if(!file) return;
  uploadFile(file).catch(err=>{
    setPill("Upload error ❌", "bad");
    console.error(err);
  });
});

generateBtn.addEventListener("click", async ()=>{
  if(!currentUploadId){
    setPill("Please upload a file first.", "bad");
    return;
  }

  setPill("Generating... (please wait)", "muted");
  generateBtn.disabled = true;

  const fd = new FormData();
  fd.append("upload_id", currentUploadId);

  const res = await fetch("/api/generate", { method:"POST", body: fd });
  const data = await res.json();

  if(!data.ok){
    setPill("Generate failed ❌ " + (data.error || ""), "bad");
    generateBtn.disabled = false;
    return;
  }

  setPill("Done ✅", "ok");

  // Cache-bust so browser loads new image
  const genUrl = data.generated_url + "?t=" + Date.now();
  showGenPreview(genUrl);

  downloadPng.href = data.download_png;
  downloadJpg.href = data.download_jpg;

  downloadRow.style.display = "flex";
  generateBtn.disabled = false;
  resetBtn.disabled = false;
});

resetBtn.addEventListener("click", clearAll);

// init
clearAll();