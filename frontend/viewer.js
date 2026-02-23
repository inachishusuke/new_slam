let rosConnection;
let viewer3D;
let pointCloudClient;
let pointCloudMaterial;

function initROS3DViewer() {
    const container = document.getElementById('canvas3d');
    if (!container) return;

    const rosUrl = `ws://${window.location.hostname}:9090`;
    rosConnection = new ROSLIB.Ros({ url: rosUrl });

    rosConnection.on('connection', function () {
        console.log('Connected to websocket server.');
    });

    rosConnection.on('error', function (error) {
        console.log('Error connecting to websocket server: ', error);
        initMock3DFallback(container);
    });

    rosConnection.on('close', function () {
        console.log('Connection to websocket server closed.');
    });

    try {
        viewer3D = new ROS3D.Viewer({
            divID: 'canvas3d',
            width: container.clientWidth,
            height: container.clientHeight,
            antialias: true,
            background: '#FFFFFF',
            cameraPose: { x: 0, y: -5, z: 2 }
        });

        viewer3D.renderer.setClearColor(0xffffff, 0);

        pointCloudClient = new ROS3D.PointCloud2({
            ros: rosConnection,
            tfClient: new ROSLIB.TFClient({
                ros: rosConnection,
                fixedFrame: 'map',
                angularThres: 0.01,
                transThres: 0.01
            }),
            topic: '/lio/pointcloud_downsampled',
            material: { size: 0.1, color: 0x000000 },
            max_pts: 50000
        });

        pointCloudMaterial = pointCloudClient.points.material;
        viewer3D.scene.add(pointCloudClient.points);

        window.addEventListener('resize', () => {
            if (viewer3D) {
                viewer3D.resize(container.clientWidth, container.clientHeight);
            }
        });
    } catch (error) {
        console.log('ROS3D init failed:', error);
        initMock3DFallback(container);
    }
}

function setCameraPose(x, y, z) {
    if (viewer3D && viewer3D.camera) {
        viewer3D.camera.position.set(x, y, z);
        if (viewer3D.cameraControls) {
            viewer3D.cameraControls.target.set(0, 0, 0);
            viewer3D.cameraControls.update();
        } else {
            viewer3D.camera.lookAt(0, 0, 0);
        }
    } else if (window.mock3DCamera) {
        window.mock3DCamera.position.set(x, y, z);
        window.mock3DCamera.lookAt(0, 0, 0);
    }
}

let isThrottled = false;

function toggleThermalThrottling(enable) {
    const overlay = document.getElementById('thermal-overlay');

    if (enable && !isThrottled) {
        isThrottled = true;
        if (overlay) overlay.classList.remove('hidden');
        if (pointCloudClient && pointCloudClient.points) {
            pointCloudClient.points.visible = false;
        }
    } else if (!enable && isThrottled) {
        isThrottled = false;
        if (overlay) overlay.classList.add('hidden');
        if (pointCloudClient && pointCloudClient.points) {
            pointCloudClient.points.visible = true;
        }
    }
}

function initMock3DFallback(container) {
    if (!container || container.querySelector('canvas')) return;

    const mock3DScene = new THREE.Scene();
    const mock3DCamera = new THREE.PerspectiveCamera(75, container.clientWidth / container.clientHeight, 0.1, 1000);

    const mock3DRenderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
    mock3DRenderer.setSize(container.clientWidth, container.clientHeight);
    container.appendChild(mock3DRenderer.domElement);

    const geometry = new THREE.BufferGeometry();
    const vertices = [];
    for (let i = 0; i < 500; i++) {
        vertices.push((Math.random() - 0.5) * 5, (Math.random() - 0.5) * 5, (Math.random() - 0.5) * 5);
    }
    geometry.setAttribute('position', new THREE.Float32BufferAttribute(vertices, 3));

    window.mock3DMaterial = new THREE.PointsMaterial({ color: 0x000000, size: 0.1 });
    const mock3DObject = new THREE.Points(geometry, window.mock3DMaterial);
    mock3DScene.add(mock3DObject);

    mock3DCamera.position.set(0, -5, 2);
    mock3DCamera.lookAt(0, 0, 0);
    window.mock3DCamera = mock3DCamera;

    window.addEventListener('resize', () => {
        mock3DCamera.aspect = container.clientWidth / container.clientHeight;
        mock3DCamera.updateProjectionMatrix();
        mock3DRenderer.setSize(container.clientWidth, container.clientHeight);
    });

    function animate3D() {
        requestAnimationFrame(animate3D);
        mock3DObject.rotation.y += 0.005;
        mock3DObject.rotation.x += 0.002;
        mock3DRenderer.render(mock3DScene, mock3DCamera);
    }
    animate3D();
}
