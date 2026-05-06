const express = require('express');
const router = express.Router();
const { serverIp } = require('../config');
router.get('/', (req, res) => res.json({ ip: serverIp }));
module.exports = router;
