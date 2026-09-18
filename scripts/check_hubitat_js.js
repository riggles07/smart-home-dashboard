/**
 * Harness: load flows/hubitat-integration.js without Node-RED and exercise the
 * Maker API device-control surface against a stubbed transport.
 * Usage: node scripts/check_hubitat_js.js
 */
"use strict";

const path = require("path");

const registered = {};
const BaseNode = class {
    constructor(type, msg, config, node) {
        this.type = type;
        this._status = [];
        this._sent = [];
    }
    on() {}
    setInterval() {}
    status(value) { this._status.push(value); }
    send(value) { this._sent.push(value); }
    log(message) { this._logs = (this._logs || []).concat(message); }
};

const RED = {
    Node: BaseNode,
    nodes: { registerType: (name, cls) => { registered[name] = cls; } }
};

const flow = require(path.join(__dirname, "..", "flows", "hubitat-integration.js"));
flow(RED);

const HubitatNode = registered["hubitat-control"];
if (!HubitatNode) { console.error("FAIL: hubitat-control not registered"); process.exit(1); }

let failures = 0;
function check(name, condition, detail) {
    if (condition) {
        console.log(`  ok   ${name}`);
    } else {
        failures++;
        console.log(`  FAIL ${name}${detail ? " -- " + detail : ""}`);
    }
}

function makeNode(transport, config) {
    const node = new HubitatNode("hubitat-control", {}, Object.assign({
        url: "http://hub.local:8080",
        appId: "17",
        accessToken: "test-token"
    }, config || {}), null);
    node.sendRequest = transport;
    return node;
}

function okTransport(calls, body) {
    return (method, url, data, callback) => {
        calls.push({ method, url });
        callback(null, { statusCode: 200, body: body || { id: "101", switch: "on" } });
    };
}

console.log("Hubitat JS device-control harness");

// --- on / off -------------------------------------------------------------
{
    const calls = [];
    const node = makeNode(okTransport(calls));
    const result = node.turnOn("101");
    check("turnOn ok", result.ok === true, JSON.stringify(result));
    check("turnOn URL", /\/apps\/api\/17\/devices\/101\/on\?access_token=test-token$/.test(calls[0].url), calls[0].url);
    check("turnOn method GET", calls[0].method === "GET");
    check("turnOn result fields", result.deviceId === "101" && result.command === "on" && result.error === null);
}
{
    const calls = [];
    const node = makeNode(okTransport(calls));
    check("turnOff ok", node.turnOff(101).ok === true);
    check("turnOff URL", calls[0].url.indexOf("/devices/101/off") !== -1, calls[0].url);
}
{
    const calls = [];
    const node = makeNode(okTransport(calls));
    check("toggle ok", node.toggle("101").ok === true);
}
{
    const calls = [];
    const node = makeNode(okTransport(calls));
    const result = node.setSwitch("101", "on");
    check("setSwitch ok", result.ok && result.value === "on");
    check("setSwitch URL", calls[0].url.indexOf("/devices/101/setSwitch/on") !== -1, calls[0].url);
}
{
    const calls = [];
    const node = makeNode(okTransport(calls));
    const result = node.setSwitch("101", "sideways");
    check("setSwitch rejects bad state", result.ok === false && result.code === "invalid_argument");
    check("setSwitch did not call hub", calls.length === 0);
}

// --- dimmer / colour ------------------------------------------------------
{
    const calls = [];
    const node = makeNode(okTransport(calls));
    check("setLevel ok", node.setLevel("101", 50).ok === true);
    check("setLevel URL", calls[0].url.indexOf("/devices/101/setLevel/50") !== -1, calls[0].url);
}
{
    const calls = [];
    const node = makeNode(okTransport(calls));
    const result = node.setLevel("101", 50, 5);
    check("setLevel+duration value", result.value === "50,5", JSON.stringify(result.value));
    check("setLevel+duration URL", calls[0].url.indexOf("/devices/101/setLevel/50%2C5") !== -1, calls[0].url);
}
{
    const calls = [];
    const node = makeNode(okTransport(calls));
    check("setLevel rejects 101", node.setLevel("101", 101).code === "invalid_argument");
    check("setLevel rejects string", node.setLevel("101", "bright").code === "invalid_argument");
    check("setLevel rejects null", node.setLevel("101", null).code === "invalid_argument");
}
{
    const calls = [];
    const node = makeNode(okTransport(calls));
    const result = node.setColor("101", 10, 90);
    check("setColor ok", result.ok === true);
    check("setColor JSON value", result.value === '{"hue":10,"saturation":90}', JSON.stringify(result.value));
    check("setColor URL encodes JSON",
        calls[0].url.indexOf("/devices/101/setColor/%7B%22hue%22%3A10%2C%22saturation%22%3A90%7D") !== -1,
        calls[0].url);
}
{
    const calls = [];
    const node = makeNode(okTransport(calls));
    const result = node.setColor("101", 10, 90, 40);
    check("setColor with level", result.ok && result.value === '{"hue":10,"saturation":90,"level":40}', JSON.stringify(result.value));
}
{
    const calls = [];
    const node = makeNode(okTransport(calls));
    check("setHue ok", node.setHue("101", 33).ok === true);
    check("setSaturation ok", node.setSaturation("101", 66).ok === true);
    check("setColorTemperature ok", node.setColorTemperature("101", 2700, 80).value === "2700,80");
    check("setColorHex ok", node.setColorHex("101", "#FF0400").value === '{"hex":"FF0400"}');
    check("setColorHex rejects bad", node.setColorHex("101", "nope").code === "invalid_argument");
    check("refresh ok", node.refreshDevice("101").ok === true);
}

// --- failure paths --------------------------------------------------------
{
    const node = makeNode((m, u, d, cb) => cb(Object.assign(new Error("timed out"), { code: "ETIMEDOUT" })));
    const result = node.turnOn("101");
    check("timeout code", result.code === "timeout", JSON.stringify(result));
}
{
    const node = makeNode(() => { throw Object.assign(new Error("connect ECONNREFUSED"), { code: "ECONNREFUSED" }); });
    const result = node.turnOn("101");
    check("sync transport throw -> connection_error", result.code === "connection_error", JSON.stringify(result));
}
{
    const node = makeNode(okTransport([]));
    const result = node.getDeviceCommands("101");
    check("getDeviceCommands ok", result.ok === true, JSON.stringify(result));
}
{
    const node = makeNode((m, u, d, cb) => cb(null, { statusCode: 401, body: { error: "Unauthorized" } }));
    const result = node.turnOff("101");
    check("http_error code", result.code === "http_error" && result.statusCode === 401, JSON.stringify(result));
    check("http_error message", /HTTP 401/.test(result.message));
}
{
    const node = makeNode((m, u, d, cb) => cb(null, { statusCode: 200, body: { error: "Device not found" } }));
    const result = node.setLevel("999", 50);
    check("unknown_device code", result.code === "unknown_device", JSON.stringify(result));
}
{
    const node = makeNode(okTransport([]));
    check("invalid device id", node.turnOn("").code === "invalid_device_id");
    check("null device id", node.turnOn(null).code === "invalid_device_id");
    check("unknown command", node.sendDeviceCommand("101", "explode").code === "unknown_command");
}
{
    const node = makeNode(okTransport([]), { accessToken: null, apiKey: null });
    delete process.env.HUBITAT_ACCESS_TOKEN;
    node.accessToken = null;
    check("missing token", node.turnOn("101").code === "missing_configuration", node.turnOn("101").code);
}
{
    const node = makeNode(okTransport([]));
    check("unsupported kwarg rejected", node.sendDeviceCommand("101", "on", "extra", "more").code === "invalid_argument");
}

// --- callbacks & dashboard surface ---------------------------------------
{
    const calls = [];
    const node = makeNode(okTransport(calls));
    let err = "unset", res = null;
    node.turnOn("101", (e, r) => { err = e; res = r; });
    check("callback success err=null", err === null && res && res.ok === true);
}
{
    const node = makeNode((m, u, d, cb) => cb(Object.assign(new Error("boom"), { code: "ETIMEDOUT" })));
    let err = null;
    node.turnOn("101", (e) => { err = e; });
    check("callback failure err set", typeof err === "string" && err.length > 0, String(err));
}
{
    const calls = [];
    const node = makeNode(okTransport(calls));
    const result = node.controlDevice({ payload: { deviceId: "101", command: "on" } });
    check("controlDevice wrapped payload", result.ok === true);
    check("controlDevice published result", node._sent.length === 1 && node._sent[0].topic === "hubitat/device/101/command");
    check("controlDevice payload ok", node._sent[0].payload.ok === true);
}
{
    const calls = [];
    const node = makeNode(okTransport(calls));
    check("controlDevice scalar value", node.controlDevice({ deviceId: "101", command: "setLevel", value: 30 }).ok === true);
    check("controlDevice list value", node.controlDevice({ deviceId: "101", command: "setLevel", value: [40, 3] }).value === "40,3");
    check("controlDevice inline args", node.handleControl({ deviceId: "101", command: "setLevel", level: 20 }).value === "20");
    check("controlDevice mapping value",
        node.controlDevice({ deviceId: "101", command: "setColor", value: { hue: 1, saturation: 100 } }).ok === true);
    check("controlDevice device_id alias", node.controlDevice({ device_id: "101", command: "on" }).ok === true);
}
{
    const node = makeNode(okTransport([]));
    check("controlDevice non-object", node.controlDevice("turn it on").code === "invalid_payload");
    check("controlDevice unknown command", node.controlDevice({ deviceId: "101", command: "explode" }).code === "unknown_command");
    check("controlDevice missing command", node.controlDevice({ deviceId: "101" }).code === "unknown_command");
}
{
    const node = makeNode(okTransport([]));
    const commands = node.supportedCommands();
    check("supportedCommands has on/off/setLevel/setColor",
        ["on", "off", "setLevel", "setColor"].every((c) => c in commands));
    check("supportedCommands setColor capability", commands.setColor.capability === "color-bulb");
}
{
    const node = makeNode(okTransport([]));
    check("token not echoed in result", JSON.stringify(node.turnOn("101")).indexOf("test-token") === -1);
}

console.log(failures ? `\n${failures} check(s) FAILED` : "\nall checks passed");
process.exit(failures ? 1 : 0);
