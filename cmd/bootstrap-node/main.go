package main

import (
	"context"
	"flag"
	"fmt"
	"log"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/libp2p/go-libp2p"
	"github.com/libp2p/go-libp2p/core/crypto"
	"github.com/libp2p/go-libp2p/core/host"
	"github.com/libp2p/go-libp2p/core/network"
	"github.com/libp2p/go-libp2p/core/peer"
	dht "github.com/libp2p/go-libp2p-kad-dht"
	"github.com/libp2p/go-libp2p/p2p/protocol/ping"
	"github.com/multiformats/go-multiaddr"
)

// BootstrapNode represents the libp2p bootstrap node
type BootstrapNode struct {
	host       host.Host
	dht        *dht.IpfsDHT
	ctx        context.Context
	cancel     context.CancelFunc
	listenAddr string
}

// NewBootstrapNode creates a new bootstrap node instance
func NewBootstrapNode(listenAddr string, privateKey crypto.PrivKey) (*BootstrapNode, error) {
	ctx, cancel := context.WithCancel(context.Background())

	// Create libp2p host
	h, err := libp2p.New(
		libp2p.Identity(privateKey),
		libp2p.ListenAddrStrings(listenAddr),
		libp2p.Ping(true),
		libp2p.EnableNATService(),
		libp2p.EnableRelay(),
	)
	if err != nil {
		cancel()
		return nil, fmt.Errorf("failed to create libp2p host: %w", err)
	}

	// Create DHT
	kadDHT, err := dht.New(ctx, h, dht.Mode(dht.ModeServer))
	if err != nil {
		h.Close()
		cancel()
		return nil, fmt.Errorf("failed to create DHT: %w", err)
	}

	// Bootstrap the DHT
	if err = kadDHT.Bootstrap(ctx); err != nil {
		kadDHT.Close()
		h.Close()
		cancel()
		return nil, fmt.Errorf("failed to bootstrap DHT: %w", err)
	}

	return &BootstrapNode{
		host:       h,
		dht:        kadDHT,
		ctx:        ctx,
		cancel:     cancel,
		listenAddr: listenAddr,
	}, nil
}

// Start begins listening for connections
func (bn *BootstrapNode) Start() error {
	log.Printf("Bootstrap node started with ID: %s", bn.host.ID())
	log.Printf("Listening on: %v", bn.host.Addrs())

	// Print multiaddrs for easy connection
	for _, addr := range bn.host.Addrs() {
		fullAddr := fmt.Sprintf("%s/p2p/%s", addr, bn.host.ID())
		log.Printf("Full multiaddr: %s", fullAddr)
	}

	// Set up connection handlers
	bn.host.Network().Notify(&network.NotifyBundle{
		ConnectedF: func(n network.Network, conn network.Conn) {
			log.Printf("New peer connected: %s", conn.RemotePeer())
			bn.logPeerStats()
		},
		DisconnectedF: func(n network.Network, conn network.Conn) {
			log.Printf("Peer disconnected: %s", conn.RemotePeer())
			bn.logPeerStats()
		},
	})

	// Start ping service
	pingService := ping.NewPingService(bn.host)
	log.Printf("Ping service started: %v", pingService)

	return nil
}

// logPeerStats logs current peer statistics
func (bn *BootstrapNode) logPeerStats() {
	peers := bn.host.Network().Peers()
	log.Printf("Current peer count: %d", len(peers))

	// Log DHT routing table size
	routingTableSize := bn.dht.RoutingTable().Size()
	log.Printf("DHT routing table size: %d", routingTableSize)
}

// GetPeers returns list of connected peers
func (bn *BootstrapNode) GetPeers() []peer.ID {
	return bn.host.Network().Peers()
}

// GetDHTStats returns DHT statistics
func (bn *BootstrapNode) GetDHTStats() map[string]interface{} {
	return map[string]interface{}{
		"routing_table_size": bn.dht.RoutingTable().Size(),
		"peer_count":         len(bn.host.Network().Peers()),
		"host_id":            bn.host.ID().String(),
		"multiaddrs":         formatMultiaddrs(bn.host.Addrs(), bn.host.ID()),
	}
}

// formatMultiaddrs formats multiaddrs with peer ID
func formatMultiaddrs(addrs []multiaddr.Multiaddr, peerID peer.ID) []string {
	result := make([]string, len(addrs))
	for i, addr := range addrs {
		result[i] = fmt.Sprintf("%s/p2p/%s", addr, peerID)
	}
	return result
}

// Close shuts down the bootstrap node
func (bn *BootstrapNode) Close() error {
	log.Println("Shutting down bootstrap node...")

	if err := bn.dht.Close(); err != nil {
		log.Printf("Error closing DHT: %v", err)
	}

	if err := bn.host.Close(); err != nil {
		log.Printf("Error closing host: %v", err)
		return err
	}

	bn.cancel()
	log.Println("Bootstrap node shut down successfully")
	return nil
}

// PeriodicStats logs statistics periodically
func (bn *BootstrapNode) PeriodicStats(interval time.Duration) {
	ticker := time.NewTicker(interval)
	defer ticker.Stop()

	for {
		select {
		case <-ticker.C:
			stats := bn.GetDHTStats()
			log.Printf("Stats: %+v", stats)
		case <-bn.ctx.Done():
			return
		}
	}
}

func main() {
	// Command line flags
	listenAddr := flag.String("listen", "/ip4/0.0.0.0/tcp/4001", "Multiaddr to listen on")
	identityFile := flag.String("identity", "", "Path to private key file (optional)")
	statsInterval := flag.Duration("stats-interval", 30*time.Second, "Interval for logging stats")
	flag.Parse()

	// Generate or load private key
	var privateKey crypto.PrivKey
	var err error

	if *identityFile != "" {
		// Load private key from file
		keyData, err := os.ReadFile(*identityFile)
		if err != nil {
			log.Fatalf("Failed to read identity file: %v", err)
		}
		privateKey, err = crypto.UnmarshalPrivateKey(keyData)
		if err != nil {
			log.Fatalf("Failed to unmarshal private key: %v", err)
		}
		log.Printf("Loaded identity from file: %s", *identityFile)
	} else {
		// Generate new key
		privateKey, _, err = crypto.GenerateKeyPair(crypto.Ed25519, -1)
		if err != nil {
			log.Fatalf("Failed to generate key pair: %v", err)
		}
		log.Println("Generated new Ed25519 identity")
	}

	// Create bootstrap node
	node, err := NewBootstrapNode(*listenAddr, privateKey)
	if err != nil {
		log.Fatalf("Failed to create bootstrap node: %v", err)
	}

	// Start the node
	if err := node.Start(); err != nil {
		log.Fatalf("Failed to start bootstrap node: %v", err)
	}

	// Start periodic stats logging
	go node.PeriodicStats(*statsInterval)

	// Handle shutdown gracefully
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, syscall.SIGINT, syscall.SIGTERM)

	<-sigChan
	log.Println("Received shutdown signal")

	if err := node.Close(); err != nil {
		log.Fatalf("Error during shutdown: %v", err)
	}
}
