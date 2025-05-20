import fs from "fs";
import fetch from "node-fetch";
import formData from "form-data";

const BOUNDS = JSON.parse(process.env.BOUNDS || "null");
const MAPBOX_TOKEN = process.env.MAPBOX_TOKEN;
const WEBHOOK_URL = process.env.WEBHOOK_URL;
if (!BOUNDS) throw new Error("BOUNDS not set");
if (!MAPBOX_TOKEN) throw new Error("MAPBOX_TOKEN not set");
if (!WEBHOOK_URL) throw new Error("WEBHOOK_URL not set");

const MARKER = "https://i.imgur.com/BnBtfv1.png";

// Function to calculate distance between two points using Haversine formula (in meters)
function calculateDistance(lat1, lon1, lat2, lon2) {
  const R = 6371e3; // Earth's radius in meters
  const φ1 = lat1 * Math.PI / 180;
  const φ2 = lat2 * Math.PI / 180;
  const Δφ = (lat2 - lat1) * Math.PI / 180;
  const Δλ = (lon2 - lon1) * Math.PI / 180;

  const a = Math.sin(Δφ / 2) * Math.sin(Δφ / 2) +
            Math.cos(φ1) * Math.cos(φ2) *
            Math.sin(Δλ / 2) * Math.sin(Δλ / 2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));

  return R * c; // Distance in meters
}

async function main() {
  let response = await fetch(
    `https://www.waze.com/live-map/api/georss?top=${BOUNDS.top}&bottom=${BOUNDS.bottom}&left=${BOUNDS.left}&right=${BOUNDS.right}&env=row&types=alerts`,
    {
      credentials: "include",
      headers: {
        "User-Agent":
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
        Accept: "application/json, text/plain, */*",
        "Accept-Language": "de,en-US;q=0.7,en;q=0.3",
        "X-KL-saas-Ajax-Request": "Ajax_Request",
        "Sec-GPC": "1",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
      },
      referrer: "https://www.waze.com/de/live-map/",
      method: "GET",
      mode: "cors",
    }
  );
  let data = await response.json();
  console.log(`${time()} | Recieved ${data.alerts.length} alerts`);

  data = data.alerts.filter((alert) => alert.type == "POLICE");

  data = data.map((alert) => {
    return {
      id: alert.uuid,
      x: alert.location.x,
      y: alert.location.y,
      nThumbsUp: alert.nThumbsUp || 0,
      reportBy: alert.reportBy,
      street: alert.street,
      since: alert.pubMillis,
    };
  });
  //read the old data and check if there are new alerts
  var oldData = [];
  if (fs.existsSync("data/data.json")) {
    oldData = JSON.parse(fs.readFileSync("data/data.json"));
  }
  
  // First filter by unique IDs
  let newAlerts = data.filter(
    (alert) => !oldData.some((oldAlert) => oldAlert.id == alert.id)
  );
  
  // Then filter out alerts that are too close to previous ones (within 200m and 3 hours)
  const THREE_HOURS_MS = 3 * 60 * 60 * 1000;
  const DISTANCE_THRESHOLD = 200; // 200 meters
  const currentTime = new Date().getTime();
  
  newAlerts = newAlerts.filter(alert => {
    // Check if this alert is too close in location and time to any old alert
    return !oldData.some(oldAlert => {
      // Check time difference (within 3 hours)
      const timeDiff = currentTime - oldAlert.since;
      if (timeDiff > THREE_HOURS_MS) return false; // Alert is older than 3 hours
      
      // Check distance (within 200m)
      const distance = calculateDistance(alert.y, alert.x, oldAlert.y, oldAlert.x);
      
      // If within time and distance threshold, we should skip this alert
      if (distance <= DISTANCE_THRESHOLD) {
        console.log(`${time()} | Skipping alert ${alert.id} - too close to existing alert ${oldAlert.id} (${Math.round(distance)}m, ${Math.round(timeDiff/60000)}min ago)`);
        return true;
      }
      return false;
    });
  });

  //if there are no new alerts, exit
  if (newAlerts.length == 0) {
    console.log(`${time()} | No new alerts found`);
    return;
  }

  console.log(`${time()} | Found ${newAlerts.length} new alerts!`);

  // get the images for the alerts
  for (let alert of newAlerts) {
    //skip if the image already exists
    if (fs.existsSync(`img/${alert.id}.png`)) {
      alert.image = `./img/${alert.id}.png`;
      continue;
    }
    const url = `https://api.mapbox.com/styles/v1/saicode/clwoyms5600y901pn0mqehko7/static/url-${encodeURIComponent(
      MARKER
    )}(${alert.x},${alert.y + 0.0005})/${alert.x},${
      alert.y
    },15/1280x720?access_token=${MAPBOX_TOKEN}&logo=false&attribution=false`;

    console.debug(url);
    let response = await fetch(url);
    //save the image in the img folder
    let buffer = await response.arrayBuffer();
    fs.writeFileSync(`img/${alert.id}.png`, Buffer.from(buffer));
    alert.image = `./img/${alert.id}.png`;
  }

  //send the new alerts to discord
  for (let alert of newAlerts) {
    let message = {
      content: "",
      embeds: [
        {
          title: "Blitzer Gefunden!",
          color: 16711680,
          footer: {
            text: "Blitzer alarm von SaiCode",
          },
          timestamp: new Date(alert.since).toISOString(),
          image: {
            url: `attachment://${alert.id}.png`,
          },
        },
      ],
      attachments: [],
    };

    const form = new formData();
    form.append("payload_json", JSON.stringify(message));
    form.append("file1", fs.createReadStream(alert.image), {
      filename: `${alert.id}.png`,
    });

    let response = await fetch(WEBHOOK_URL, {
      method: "POST",
      body: form,
      headers: form.getHeaders(),
    });
    console.log(`${time()} | Sent alert ${alert.id} to discord!`);

    //delete the image
    fs.unlinkSync(alert.image);
  }
  //write to the console, modify since to be more readable
  console.table(
    newAlerts.map((alert) => {
      alert.since = new Date(alert.since).toLocaleString("de-DE", {
        timeZone: "Europe/Berlin",
      });
      return alert;
    })
  );
  //write the data to the file
  fs.writeFileSync("data/data.json", JSON.stringify(data));
}

const time = () => new Date().toLocaleString("de-DE", { timeZone: "Europe/Berlin", dateStyle: "short", timeStyle: "medium" });

// if ctl+c is pressed, exit the program and delete the img files
process.on("SIGINT", () => {
  console.log(`${time()} | Stopping the program and deleting the images!`);
  fs.readdirSync("img").forEach((file) => {
    fs.unlinkSync(`img/${file}`);
  });
  process.exit();
});


while (true) {
  main();
  await new Promise((resolve) => setTimeout(resolve, 60000));
}