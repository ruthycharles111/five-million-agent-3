const express = require('express');
const bcrypt = require('bcryptjs');
const jwt = require('jsonwebtoken');
const db = require('../db');
const { jwtSecret } = require('../config');
const router = express.Router();

router.post('/register', (req, res) => {
  try {
    const { email, password, first_name, last_name, phone } = req.body;
    if (!email || !password) return res.status(400).json({ error: 'Email and password required' });
    const existing = db.prepare('SELECT id FROM users WHERE email = ?').get(email);
    if (existing) return res.status(409).json({ error: 'Email already registered' });
    const salt = bcrypt.genSaltSync(10);
    const hash = bcrypt.hashSync(password, salt);
    const stmt = db.prepare('INSERT INTO users (email, password, first_name, last_name, phone) VALUES (?, ?, ?, ?, ?)');
    const result = stmt.run(email, hash, first_name || null, last_name || null, phone || null);
    const userId = result.lastInsertRowid;
    db.prepare('INSERT INTO wallets (user_id, balance) VALUES (?, ?)').run(userId, 0.0);
    const token = jwt.sign({ id: userId, email }, jwtSecret, { expiresIn: '7d' });
    res.status(201).json({ message: 'Registration successful', token, user: { id: userId, email } });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: 'Internal server error' });
  }
});

router.post('/login', (req, res) => {
  try {
    const { email, password } = req.body;
    if (!email || !password) return res.status(400).json({ error: 'Email and password required' });
    const user = db.prepare('SELECT * FROM users WHERE email = ?').get(email);
    if (!user) return res.status(401).json({ error: 'Invalid credentials' });
    const valid = bcrypt.compareSync(password, user.password);
    if (!valid) return res.status(401).json({ error: 'Invalid credentials' });
    const token = jwt.sign({ id: user.id, email: user.email }, jwtSecret, { expiresIn: '7d' });
    res.json({ message: 'Login successful', token, user: { id: user.id, email: user.email } });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: 'Internal server error' });
  }
});

module.exports = router;
