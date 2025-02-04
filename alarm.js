import fs from "fs";
import fetch from "node-fetch";
import formData from "form-data";

const  BOUNDS = {
  top: 49.03360094218811,
  bottom: 48.96663726218302,
  left: 12.000735049845973,
  right: 12.152449374797143,
};

/*
Test whole of Regensburg
const BOUNDS = {
  top: 49.079626571153625,
  bottom: 48.945733047592306,
  left: 11.878446875117428,
  right: 12.300733862422117,
}; 
*/

const MARKER = "https://i.imgur.com/BnBtfv1.png";

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
  if (fs.existsSync("data.json")) {
    oldData = JSON.parse(fs.readFileSync("data.json"));
  }
  let newAlerts = data.filter(
    (alert) => !oldData.some((oldAlert) => oldAlert.id == alert.id)
  );

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
    },15/1280x720?access_token=${process.env.MAPBOX_TOKEN}&logo=false&attribution=false`;

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

    let response = await fetch(process.env.WEBHOOK_URL, {
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
  fs.writeFileSync("data.json", JSON.stringify(data));
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