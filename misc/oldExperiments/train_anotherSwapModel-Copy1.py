import torch
import torchvision.transforms as transforms
from torchvision.utils import make_grid

from utils.storage import save_trained
from utils.device import setup_device
from utils.losses import ReconstructionLoss, SceneLatentLoss, LightLatentLoss
import utils.tensorboard as tensorboard

from utils.dataset import InputTargetGroundtruthDataset, DifferentScene
from torch.utils.data import DataLoader

from models.anOtherSwapNetSmaller import SwapModel


# Get used device
GPU_IDS = [1]
device = setup_device(GPU_IDS)

# Parameters
NAME = 'anOtherSwapNet'
BATCH_SIZE = 50
NUM_WORKERS = 8
EPOCHS = 30
SIZE = 256

# Configure training objects
model = SwapModel().to(device)
optimizer = torch.optim.Adam(model.parameters(), weight_decay=0)

# Losses
reconstruction_loss = ReconstructionLoss().to(device)
scene_latent_loss = SceneLatentLoss().to(device)
light_latent_loss = LightLatentLoss().to(device)

# Configure dataloader
train_dataset = InputTargetGroundtruthDataset(locations=['scene_abandonned_city_54'],
                                              transform=transforms.Resize(SIZE),
                                              pairing_strategies=[DifferentScene()])
train_dataloader  = DataLoader(train_dataset, batch_size=BATCH_SIZE, shuffle=True, num_workers=NUM_WORKERS)
DATASET_SIZE = len(train_dataset)
print(f'Dataset contains {DATASET_SIZE} samples.')
print(f'Running with batch size: {BATCH_SIZE} for {EPOCHS} epochs.')

# Configure tensorboard
writer = tensorboard.setup_summary_writer(NAME)
tensorboard_process = tensorboard.start_tensorboard_process()
SHOWN_SAMPLES = 3
VISUALIZATION_FREQ = 100  # every how many batches tensorboard is updated with new images
print(f'{SHOWN_SAMPLES} samples will be visualized every {VISUALIZATION_FREQ} batches.')

# Train loop
for epoch in range(1, EPOCHS+1):
    train_loss, train_reconstruction_loss, train_scene_latent_loss_1, train_scene_latent_loss_2, train_light_latent_loss_1, train_light_latent_loss_2, train_score = 0., 0., 0., 0., 0., 0., 0.
    print(f'Epoch {epoch}:')
    
    step = 0
    sub_train_loss, sub_train_reconstruction_loss, sub_train_scene_latent_loss_1, sub_train_scene_latent_loss_2, sub_train_light_latent_loss_1, sub_train_light_latent_loss_2, sub_train_score = 0., 0., 0., 0., 0., 0., 0.
        
    for batch_idx, batch in enumerate(train_dataloader):
        
        input_image = batch[0][0]['image'].to(device)
        target_image = batch[0][1]['image'].to(device)
        groundtruth_image = batch[1]['image'].to(device)
        input_color = batch[0][0]['color'].to(device)
        target_color = batch[0][1]['color'].to(device)
        input_direction = batch[0][0]['direction'].to(device)
        target_direction = batch[0][1]['direction'].to(device)
        
        # Forward
        model.train()     
        
        output = model(input_image, target_image, groundtruth_image, encode_pred = True)
        
        groundtruth_scene_latent, input_scene_latent, target_scene_latent, relighted_scene_latent, \
        groundtruth_light_latent, input_light_latent, target_light_latent, relighted_light_latent, \
        groundtruth_light_predic, input_light_predic, target_light_predic, \
        relighted_image, relighted_image2 = output  
        
        re = reconstruction_loss(relighted_image, groundtruth_image)
        s1 = scene_latent_loss(input_scene_latent, groundtruth_scene_latent, ref1=target_scene_latent, ref2=groundtruth_scene_latent)
        s2 = scene_latent_loss(input_scene_latent, relighted_scene_latent, ref1=target_scene_latent, ref2=groundtruth_scene_latent)
        l1 = light_latent_loss(target_light_latent, groundtruth_light_latent, ref1=input_light_latent, ref2=groundtruth_light_latent)
        l2 = light_latent_loss(target_light_latent, relighted_light_latent, ref1=input_light_latent, ref2=groundtruth_light_latent)
        loss = re + s1 + s2 + l1 + l2
        
        train_loss += loss.item()
        sub_train_loss += loss.item()
        train_reconstruction_loss += re.item()
        sub_train_reconstruction_loss += re.item()
        train_scene_latent_loss_1 += s1.item()
        sub_train_scene_latent_loss_1 += s1.item()
        train_scene_latent_loss_2 += s2.item()
        sub_train_scene_latent_loss_2 += s2.item()
        train_light_latent_loss_1 += l1.item()
        sub_train_light_latent_loss_1 += l1.item()
        train_light_latent_loss_2 += l2.item()
        sub_train_light_latent_loss_2 += l2.item()
        
        ref = reconstruction_loss(input_image, groundtruth_image).item()
        train_score += ref / re.item()
        sub_train_score += ref / re.item()
        

        # Backward
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()

        
        # Visualize current progress
        if (1+batch_idx) % VISUALIZATION_FREQ == 0:
            writer.add_image('Visualization/1-Input', make_grid(input_image[:SHOWN_SAMPLES]), step)
            writer.add_image('Visualization/2-Target', make_grid(target_image[:SHOWN_SAMPLES]), step)
            writer.add_image('Visualization/3-Ground-truth', make_grid(groundtruth_image[:SHOWN_SAMPLES]), step)
            writer.add_image('Visualization/4-Relighted', make_grid(relighted_image[:SHOWN_SAMPLES]), step)
            writer.add_image('Visualization/5-Relighted2', make_grid(relighted_image2[:SHOWN_SAMPLES]), step)

            writer.add_image('Light-latent/1-Input', make_grid(input_light_latent[:SHOWN_SAMPLES]), step)
            writer.add_image('Light-latent/2-Target', make_grid(target_light_latent[:SHOWN_SAMPLES]), step)
            writer.add_image('Light-latent/3-Ground-truth', make_grid(groundtruth_light_latent[:SHOWN_SAMPLES]), step)
            writer.add_image('Light-latent/4-Relighted', make_grid(relighted_light_latent[:SHOWN_SAMPLES]), step)
            
            step += 1
            writer.add_scalar(f'{VISUALIZATION_FREQ}Batches-loss/1-Loss', sub_train_loss, step)
            writer.add_scalars(f'{VISUALIZATION_FREQ}Batches-Loss/2-Components', {
                '1-Reconstruction': sub_train_reconstruction_loss,
                '2-SceneLatent1': sub_train_scene_latent_loss_1,
                '3-SceneLatent2': sub_train_scene_latent_loss_2,
                '4-LightLatent1': sub_train_light_latent_loss_1,
                '5-LightLatent2': sub_train_light_latent_loss_2
            }, step)
            writer.add_scalar(f'{VISUALIZATION_FREQ}Batches-score/1-Score', sub_train_score, step)
            sub_train_loss, sub_train_reconstruction_loss, sub_train_scene_latent_loss_1, sub_train_scene_latent_loss_2, sub_train_light_latent_loss_1, sub_train_light_latent_loss_1, sub_train_score = 0., 0., 0., 0., 0., 0., 0.
        
       
    # Evaluate
    model.eval()
    # TODO: Add test set evaluation here

    # Update tensorboard training losses
    writer.add_scalar('Loss/1-Loss', train_loss, epoch)
    writer.add_scalars('Loss/2-Components', {
        '1-Reconstruction': train_reconstruction_loss,
        '2-SceneLatent1': train_scene_latent_loss_1,
        '3-SceneLatent2': train_scene_latent_loss_2,
        '4-LightLatent1': train_light_latent_loss_1,
        '5-LightLatent2': train_light_latent_loss_2
    }, epoch)
    writer.add_scalar('Score/1-Score', train_loss, epoch)

# Store trained model
save_trained(model, NAME)

# Terminate tensorboard
tensorboard.stop_tensorboard_process(tensorboard_process)
