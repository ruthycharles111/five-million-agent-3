require('dotenv').config();
const express = require('express');
const cors = require('cors');
const { port } = require('./config');

const authRoutes = require('./routes/auth');
const walletRoutes = require('./routes/wallet');
const transferRoutes = require('./routes/transfer');
const airtimeDataRoutes = require('./routes/airtimeData');
const accountRoutes = require('./routes/accounts');
const virtualAccountRoutes = require('./routes/virtualAccount');
const ipRoutes = require('./routes/ip');
const webhookRoutes = require('./routes/webhook');

const app = express();
app.use(cors());

// Webhook MUST be before JSON parsing
app.use('/webhook', express.raw({ type: 'application/json' }), webhookRoutes);
app.use(express.json());

app.use('/api/auth', authRoutes);
app.use('/api/wallet', walletRoutes);
app.use('/api/transfer', transferRoutes);
app.use('/api', airtimeDataRoutes);
app.use('/api/accounts', accountRoutes);
app.use('/api/virtual-account', virtualAccountRoutes);
app.use('/api/ip', ipRoutes);
app.get('/api/health', (req, res) => res.send('Ajo API running'));

app.listen(port, () => console.log(`Ajo API server running on port ${port}`));
