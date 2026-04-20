import { BrowserWindow, app } from "electron";
import path from "path";
import { fileURLToPath } from "url";
import { spawn, spawnSync } from "child_process";
import { existsSync } from "fs";

//#region electron/main.js
var __dirname = path.dirname(fileURLToPath(import.meta.url));
var mainWindow;
let servicesStopped = false;

function findProjectRoot() {
	if (!app.isPackaged) return path.join(__dirname, "../..");

	// Remonte depuis le .exe jusqu'à trouver docker-compose.yml
	let dir = path.dirname(app.getPath("exe"));
	for (let i = 0; i < 6; i++) {
		if (existsSync(path.join(dir, "docker-compose.yml"))) return dir;
		const parent = path.dirname(dir);
		if (parent === dir) break;
		dir = parent;
	}
	return path.dirname(app.getPath("exe"));
}

const projectRoot = findProjectRoot();

function startServices() {
	console.log("Starting Docker services from:", projectRoot);
	const docker = spawn("docker", ["compose", "up", "-d"], {
		cwd: projectRoot,
		stdio: "pipe"
	});
	docker.on("error", (err) => console.error("Docker error:", err.message));
	docker.stderr.on("data", (d) => process.stdout.write("[docker] " + d.toString()));
}

function stopServices() {
	if (servicesStopped) return;
	servicesStopped = true;
	console.log("Stopping Docker services...");
	spawnSync("docker", ["compose", "down"], {
		cwd: projectRoot,
		stdio: "pipe",
		timeout: 15000
	});
}

function createWindow() {
	mainWindow = new BrowserWindow({
		width: 1200,
		height: 850,
		minWidth: 1e3,
		minHeight: 700,
		backgroundColor: "#1e1e1e",
		autoHideMenuBar: true,
		icon: path.join(__dirname, "../src/assets/logo-app.png"),
		webPreferences: {
			contextIsolation: true,
			nodeIntegration: false,
			preload: path.join(__dirname, "preload.mjs")
		}
	});
	if (process.env.VITE_DEV_SERVER_URL) mainWindow.loadURL(process.env.VITE_DEV_SERVER_URL).catch(() => {
		setTimeout(() => mainWindow.loadURL(process.env.VITE_DEV_SERVER_URL), 1e3);
	});
	else mainWindow.loadFile(path.join(__dirname, "../dist/index.html"));
}

app.whenReady().then(() => {
	startServices();
	createWindow();
	app.on("activate", () => {
		if (BrowserWindow.getAllWindows().length === 0) createWindow();
	});
});

app.on("before-quit", () => {
	stopServices();
});

app.on("window-all-closed", () => {
	if (process.platform !== "darwin") {
		stopServices();
		app.quit();
	}
});
//#endregion
