/* global require, process, __dirname */
// production-server.js
const path = require('path');
const express = require('express');

const app = express();
const dir = process.pkg ? path.dirname(process.argv[0]) : __dirname;

app.use(express.static(path.join(dir, 'dist')));

app.listen(3000, () => {
  console.log('Server running on http://localhost:3000');
});