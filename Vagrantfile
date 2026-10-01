SERVICES = {
  "database" => { ip: "192.168.56.20", memory: 1024 },
  "auth" => { ip: "192.168.56.21", memory: 768 },
  "bank" => { ip: "192.168.56.22", memory: 768 },
  "gateway" => { ip: "192.168.56.23", memory: 512 },
}.freeze

Vagrant.configure("2") do |config|
  config.vm.box = "ubuntu/jammy64"
  config.vm.boot_timeout = 600

  SERVICES.each do |name, settings|
    config.vm.define name do |machine|
      machine.vm.hostname = "mnm-#{name}"
      machine.vm.network "private_network", ip: settings[:ip]

      if name == "gateway"
        machine.vm.network "forwarded_port",
                           guest: 80,
                           host: 8081,
                           host_ip: "127.0.0.1"
      end

      machine.vm.provider "virtualbox" do |virtualbox|
        virtualbox.name = "banco-mnm-#{name}"
        virtualbox.memory = settings[:memory]
        virtualbox.cpus = 1
      end

      machine.vm.provision "shell", path: "vagrant/provision.sh", args: [name]
    end
  end
end