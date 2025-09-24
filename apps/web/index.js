const http = require("http");
const port = process.env.PORT || 3000;

http.createServer((req, res) => {
  res.end("Censorly Web OK");
}).listen(port);

console.log("Web listening on", port);
